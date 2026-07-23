#!/usr/bin/env python3
"""
MERIDIAN Grid  –  EU-weiter zonaler Stromnetz-Simulator
========================================================

v2: das GESAMTE europäische Verbundnetz.

Vier Synchronzonen, wie in der Realität:
  CE   Kontinentaleuropa (inkl. Baltikum – seit Feb 2025 synchron!)
  N    Nordic (NO/SE/FI/DK-Ost)
  GB   Großbritannien
  IE   Irland (SEM, gesamte Insel)

Zwei Kanten-Typen, wie auf dem Nagelbrett:
  AC   Wechselstrom-Kuppelleitung. Der Fluss ergibt sich aus der Physik
       (Kirchhoff): F = b · Δθ. Niemand "steuert" ihn.
  DC   HVDC-Kabel ("Draht mit Schalter"). Der Fluss ist ein SOLLWERT, den
       der Betreiber einstellt – er gehorcht dem Fahrplan, nicht Kirchhoff.
       Alle Verbindungen ZWISCHEN Synchronzonen sind DC; einige existieren
       auch innerhalb (z.B. ALEGrO DE–BE, Storebælt DK1–DK2).

Der Lastfluss wird je Synchronzone separat gelöst (jede hat ihren eigenen
verteilten Slack = gemeinsame Frequenzregelung). DC-Sollwerte wirken als
feste Ein-/Ausspeisung an ihren Endpunkten – so koppeln sich die Zonen.

Alle Kapazitäten/Suszeptanzen: dokumentierte Plausibilitätsannahmen, per
A11-Kalibrierung (meridian_grid_live.py) an Messwerte anpassbar.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# 1) ZONEN  –  39 Knoten in 4 Synchronzonen
# ══════════════════════════════════════════════════════════════════════════════
# base_load/gen: plausibler Werktag-Schnitt (MW) als Default; im Live-Betrieb
# aus ENTSO-E überschrieben. NO/SE sind in ihre realen Gebotszonen aufgeteilt,
# weil die internen Engpässe (z.B. SE2→SE3) netzprägend sind.
#
# Bewusst NICHT enthalten (und warum):
#   UA/MD  – seit 2022 CE-notsynchronisiert, aber Datenlage kriegsbedingt
#            lückig; NTC klein. Ehrlicher wegzulassen als halb zu raten.
#   LU     – Teil der Gebotszone DE-LU, steckt in den DE-Zahlen.
#   MT/CY  – Inselnetze ohne/mit minimaler Kupplung.
#   TR     – CE-synchron, aber außerhalb EU-Datenraum.

@dataclass
class Zone:
    code: str
    name: str
    sync: str                  # CE | N | GB | IE
    lat: float
    lon: float
    base_load: float
    base_gen: float
    gen: dict = field(default_factory=dict)


def _mix(nuclear=0, coal=0, gas=0, hydro=0, wind=0, solar=0, biomass=0, other=0):
    return dict(nuclear=nuclear, coal=coal, gas=gas, hydro=hydro,
                wind=wind, solar=solar, biomass=biomass, other=other)


def _z(code, name, sync, lat, lon, load, **mix):
    g = _mix(**mix)
    return Zone(code, name, sync, lat, lon, load, sum(g.values()), g)


ZONES: dict[str, Zone] = {z.code: z for z in [
    # ── Kontinentaleuropa (CE) ────────────────────────────────────────────────
    _z("FR", "Frankreich",  "CE", 46.6,   2.4, 58000, nuclear=45000, gas=3000, hydro=9000, wind=4000, solar=1000, biomass=1000),
    _z("DE", "Deutschland", "CE", 51.2,  10.4, 62000, coal=14000, gas=8000, hydro=3000, wind=28000, solar=6000, biomass=5000),
    _z("NL", "Niederlande", "CE", 52.2,   5.3, 13000, gas=6000, coal=1500, wind=3500, solar=1000, other=500),
    _z("BE", "Belgien",     "CE", 50.6,   4.6,  9500, nuclear=4000, gas=2500, wind=1500, solar=700, other=300),
    _z("CH", "Schweiz",     "CE", 46.9,   8.2,  7000, nuclear=2200, hydro=5500, solar=200, other=100),
    _z("AT", "Österreich",  "CE", 47.6,  14.1,  8000, hydro=6000, gas=900, wind=1000, solar=200, biomass=100),
    _z("IT", "Italien",     "CE", 43.5,  11.5, 44000, gas=21000, hydro=7000, solar=6000, wind=2500, coal=1000, other=2500),
    _z("SI", "Slowenien",   "CE", 46.1,  14.8,  1600, nuclear=700, hydro=600, coal=300, other=100),
    _z("HR", "Kroatien",    "CE", 45.3,  15.9,  2200, hydro=1200, gas=400, wind=300, other=100),
    _z("CZ", "Tschechien",  "CE", 49.8,  15.5,  8000, nuclear=3800, coal=3000, gas=500, solar=800, other=700),
    _z("SK", "Slowakei",    "CE", 48.7,  19.7,  3200, nuclear=1900, hydro=700, gas=500, other=300),
    _z("HU", "Ungarn",      "CE", 47.2,  19.4,  5500, nuclear=1900, gas=1200, solar=800, other=300),
    _z("PL", "Polen",       "CE", 52.1,  19.4, 22000, coal=16000, gas=2000, wind=3000, solar=1000, other=500),
    _z("RO", "Rumänien",    "CE", 45.9,  25.0,  7500, hydro=2500, nuclear=1300, gas=1500, coal=1200, wind=1000, solar=500),
    _z("BG", "Bulgarien",   "CE", 42.7,  25.3,  4500, nuclear=2000, coal=1500, hydro=800, gas=300, solar=400),
    _z("GR", "Griechenland","CE", 39.3,  22.5,  6500, gas=3000, hydro=1200, wind=1500, solar=1500, coal=300, other=200),
    _z("RS", "Serbien",     "CE", 44.2,  20.9,  4500, coal=3000, hydro=1400, gas=300),
    _z("BA", "Bosnien-H.",  "CE", 44.2,  17.8,  1700, coal=1100, hydro=700),
    _z("ME", "Montenegro",  "CE", 42.7,  19.3,   550, hydro=350, coal=220),
    _z("MK", "Nordmazedon.","CE", 41.6,  21.7,  1100, coal=500, hydro=250, gas=250, other=150),
    _z("AL", "Albanien",    "CE", 41.1,  20.0,  1000, hydro=1050),
    _z("ES", "Spanien",     "CE", 40.3,  -3.7, 30000, nuclear=6000, gas=6000, hydro=4000, wind=8000, solar=6000, other=1000),
    _z("PT", "Portugal",    "CE", 39.6,  -8.0,  6000, gas=1500, hydro=1500, wind=2000, solar=1000, other=200),
    _z("DK1","Dänemark W",  "CE", 56.0,   9.2,  2400, wind=2600, gas=300, coal=300, biomass=500),
    # Baltikum – seit 8. Februar 2025 von BRELL getrennt und CE-synchron:
    _z("EE", "Estland",     "CE", 58.8,  25.5,   950, other=500, wind=250, solar=150, biomass=150),
    _z("LV", "Lettland",    "CE", 56.9,  24.9,   800, hydro=500, gas=300, wind=100),
    _z("LT", "Litauen",     "CE", 55.3,  23.9,  1500, wind=500, hydro=100, gas=200, solar=200, other=100),
    # ── Nordic (N) ────────────────────────────────────────────────────────────
    _z("NO1","Norwegen SO", "N",  60.5,  10.8,  4500, hydro=4200, wind=100),
    _z("NO2","Norwegen SW", "N",  58.5,   7.5,  4200, hydro=6500, wind=300),
    _z("NO3","Norwegen Mi", "N",  63.5,  10.0,  2600, hydro=2300, wind=400),
    _z("NO4","Norwegen N",  "N",  68.5,  17.0,  1900, hydro=2400, wind=400),
    _z("NO5","Norwegen W",  "N",  60.9,   6.2,  1900, hydro=2800),
    _z("SE1","Schweden N",  "N",  66.5,  20.5,  1300, hydro=2800, wind=700),
    _z("SE2","Schweden NMi","N",  62.8,  15.5,  1500, hydro=3200, wind=1300),
    _z("SE3","Schweden SMi","N",  59.5,  15.5,  9500, nuclear=6100, hydro=1200, wind=1800, solar=300),
    _z("SE4","Schweden S",  "N",  56.5,  14.2,  2600, wind=1000, other=400, solar=200),
    _z("FI", "Finnland",    "N",  62.5,  26.0,  9500, nuclear=4400, hydro=1500, wind=2200, biomass=1200, other=400),
    _z("DK2","Dänemark O",  "N",  55.5,  11.9,  1600, wind=1000, biomass=400, coal=200),
    # ── Großbritannien (GB) ───────────────────────────────────────────────────
    _z("GB", "Großbritan.", "GB", 53.0,  -1.8, 32000, gas=14000, wind=9000, nuclear=4500, solar=1500, biomass=2500, other=800),
    # ── Irland (IE, gesamte Insel = SEM) ──────────────────────────────────────
    _z("IE", "Irland (SEM)","IE", 53.3,  -7.8,  5200, gas=2800, wind=1800, other=500, coal=200),
]}

SYNC_ZONES = ("CE", "N", "GB", "IE")


# ══════════════════════════════════════════════════════════════════════════════
# 2) KANTEN  –  AC-Kuppelleitungen + HVDC-Kabel
# ══════════════════════════════════════════════════════════════════════════════
# AC: suscept = relative Suszeptanz (Fluss folgt Kirchhoff), ntc = Limit MW.
# DC: suscept irrelevant; setpoint = Sollwert MW (+ = a→b). Default-Sollwerte
#     sind typische Handelsrichtungen; im Live-Betrieb aus A11-Messung gesetzt.

@dataclass
class Line:
    a: str
    b: str
    suscept: float
    ntc: float
    kind: str = "AC"         # "AC" | "DC"
    setpoint: float = 0.0    # nur DC: Sollwert MW (+: a→b)
    label: str = ""          # nur DC: Kabelname

def _dc(a, b, ntc, setpoint=0.0, label=""):
    return Line(a, b, 0.0, ntc, "DC", setpoint, label)


INTERCONNECTORS: list[Line] = [
    # ── CE: Kern (wie v1) ─────────────────────────────────────────────────────
    Line("FR", "DE", 12.0, 4800),
    Line("FR", "BE",  9.0, 4300),
    Line("FR", "CH", 10.0, 3700),
    Line("FR", "IT",  8.0, 4350),
    Line("FR", "ES",  8.0, 2800),
    Line("DE", "NL", 11.0, 5000),
    Line("DE", "CH",  9.0, 4600),
    Line("DE", "AT", 14.0, 5400),
    Line("DE", "CZ", 10.0, 2100),
    Line("DE", "PL",  7.0, 3000),
    Line("NL", "BE",  8.0, 2400),
    Line("CH", "AT",  7.0, 1700),
    Line("CH", "IT", 10.0, 4240),
    Line("AT", "IT",  2.0,  455),   # real 1 schwache Leitung
    Line("AT", "CZ",  6.0,  900),
    Line("AT", "HU",  7.0, 1200),
    Line("AT", "SI",  6.0,  950),
    Line("CZ", "SK",  8.0, 1100),
    Line("CZ", "PL",  6.0,  600),
    Line("SK", "HU",  7.0, 1300),
    Line("SK", "PL",  4.0,  500),
    Line("HU", "SI",  4.0,  600),
    Line("HU", "HR",  5.0,  900),
    Line("SI", "HR",  5.0, 1200),
    Line("SI", "IT",  4.0,  680),
    Line("ES", "PT",  9.0, 3400),
    # ALEGrO: DC-Kabel INNERHALB der CE-Zone (einziges DE–BE-Kabel)
    _dc("DE", "BE", 1000, +300, "ALEGrO"),
    # ── CE: Südost-Erweiterung (Balkan) ──────────────────────────────────────
    Line("HU", "RO",  6.0, 1300),
    Line("HU", "RS",  5.0, 1200),
    Line("HR", "RS",  4.0,  600),
    Line("HR", "BA",  5.0, 1000),
    Line("RS", "BA",  4.0,  700),
    Line("RS", "RO",  4.0, 1000),
    Line("RS", "BG",  4.0,  600),
    Line("RS", "ME",  3.0,  600),
    Line("RS", "MK",  3.0,  550),
    Line("RO", "BG",  5.0, 1000),
    Line("BG", "GR",  4.0,  800),
    Line("BG", "MK",  3.0,  500),
    Line("GR", "MK",  3.0,  550),
    Line("GR", "AL",  3.0,  400),
    Line("ME", "AL",  3.0,  500),
    Line("ME", "BA",  3.0,  550),
    _dc("IT", "GR",  500,  -150, "GRITA"),    # typ. GR→IT
    _dc("IT", "ME",  600,  -250, "MONITA"),   # typ. ME→IT
    # ── CE: Norden – DK-West (Jütland ist CE-synchron!) ──────────────────────
    Line("DE", "DK1", 6.0, 2500),
    _dc("DK1","NL", 700, +200, "COBRAcable"),
    # ── CE: Baltikum (LitPol seit Feb 2025 AC) ───────────────────────────────
    Line("PL", "LT",  4.0,  500),
    Line("LT", "LV",  5.0, 1300),
    Line("LV", "EE",  5.0, 1100),
    # ── Nordic intern (AC) ───────────────────────────────────────────────────
    Line("NO1","NO2", 8.0, 3500),
    Line("NO1","NO3", 3.0,  700),   # Zubringer Trondheim-Oslo
    Line("NO1","NO5", 7.0, 3900),
    Line("NO2","NO5", 3.0,  600),
    Line("NO3","NO4", 5.0, 1200),
    Line("NO3","NO5", 4.0,  500),
    Line("NO1","SE3", 6.0, 2100),
    Line("NO3","SE2", 4.0, 1000),
    Line("NO4","SE1", 4.0,  700),
    Line("NO4","SE2", 3.0,  300),
    Line("SE1","SE2", 8.0, 3300),
    Line("SE2","SE3", 9.0, 7300),
    Line("SE3","SE4", 8.0, 5400),
    Line("SE1","FI",  5.0, 1500),
    Line("SE3","FI",  4.0, 1200),   # Fenno-Skan ist DC, RAC-Nord AC – vereinfacht AC
    Line("SE4","DK2", 6.0, 1700),   # Öresund: AC
    # ── DC-Kabel ZWISCHEN den Synchronzonen ──────────────────────────────────
    # CE ↔ Nordic
    _dc("DK1","DK2",  600, +200, "Storebælt"),
    _dc("DK1","NO2", 1700, -800, "Skagerrak"),
    _dc("DK1","SE3",  740, -300, "Konti-Skan"),
    _dc("DE", "DK2",  600, -200, "Kontek"),
    _dc("DE", "SE4",  615, -300, "Baltic Cable"),
    _dc("PL", "SE4",  600, -200, "SwePol"),
    _dc("DE", "NO2", 1400, -900, "NordLink"),
    _dc("NL", "NO2",  700, -500, "NorNed"),
    _dc("LT", "SE4",  700, -250, "NordBalt"),
    _dc("EE", "FI",  1000, -350, "EstLink 1+2"),
    # CE ↔ GB
    _dc("FR", "GB",  4000, +1500, "IFA/IFA2/ElecLink"),
    _dc("BE", "GB",  1000,  +300, "Nemo Link"),
    _dc("NL", "GB",  1000,  +300, "BritNed"),
    _dc("DK1","GB",  1400,  +500, "Viking Link"),
    # Nordic ↔ GB
    _dc("NO2","GB",  1400,  +800, "North Sea Link"),
    # GB ↔ IE
    _dc("GB", "IE",  1000,  +300, "EWIC/Greenlink"),
    _dc("GB", "IE",   500,  +150, "Moyle"),
]


# ══════════════════════════════════════════════════════════════════════════════
# 3) NETZFREQUENZ  –  quasistationär nach Primärregelung
# ══════════════════════════════════════════════════════════════════════════════
# Der verteilte Slack IST die Primärregelung (FCR). Sie hält die Frequenz
# nicht bei 50,000 Hz, sondern hinterlässt eine quasistationäre Abweichung:
#     Δf = −ΔP_regel / λ        (λ = Netzleistungszahl der Synchronzone)
# CE-Auslegung: 3000 MW FCR für 200 mHz  →  λ_CE = 15 GW/Hz (ENTSO-E-Design).
# Jede INSEL bekommt ihre eigene Frequenz; λ skaliert mit ihrem Anteil an
# der Erzeugung der Ursprungs-Synchronzone – eine kleine abgetrennte Insel
# mit Defizit stürzt frequenzmäßig ab, während der Rest kaum zuckt.
#
# WICHTIG: gerechnet wird die Abweichung RELATIV ZUM UNGESTÖRTEN ZUSTAND
# (freq_reference). Die Daten-Restbilanz der Kalibrierung ist ein Mess-
# artefakt, keine reale Frequenzabweichung – ohne Referenz stünde Europa
# fälschlich bei 49,8x Hz. Start = 50,000; Eingriffe bewegen die Frequenz.

FREQ_LAMBDA_MW_HZ = {"CE": 15000.0, "N": 6000.0, "GB": 2500.0, "IE": 450.0}

# Reale Schutz-/Betriebsstufen (CE-orientiert, mHz-Abweichung von 50 Hz):
def freq_status(dev_mhz: float) -> tuple[str, str]:
    if dev_mhz >= 1500:  return "collapse", "KOLLAPS – Erzeuger-Schutzabschaltung (≥51,5 Hz)"
    if dev_mhz >= 200:   return "emergency", "ÜBERFREQUENZ – PV-Schutzabschaltungen (≥50,2 Hz)"
    if dev_mhz >= 100:   return "alert", "ERHÖHT"
    if dev_mhz > -100:   return "normal", "NORMAL"
    if dev_mhz > -200:   return "alert", "ABGESENKT"
    if dev_mhz > -1000:  return "emergency", "KRITISCH – FCR-Grenze erreicht (≤49,8 Hz)"
    if dev_mhz > -2500:  return "emergency", "LASTABWURF – UFLS aktiv (≤49,0 Hz)"
    return "collapse", "SYSTEMKOLLAPS (≤47,5 Hz)"


# ══════════════════════════════════════════════════════════════════════════════
# 4) LASTFLUSS  –  je Synchronzone, DC als Injektion
# ══════════════════════════════════════════════════════════════════════════════

class GridModel:
    """
    EU-weiter zonaler Lastfluss.

    Ablauf pro solve():
      1. DC-Sollwerte (inkl. Schocks) als feste Injektionen an den Endpunkten
      2. je Synchronzone: verteilter Slack über die Zonen DIESER Synchronzone
         (Frequenzregelung endet an der Synchronzonen-Grenze!)
      3. je Synchronzone: B-Matrix der AC-Kanten, θ lösen, AC-Flüsse
      4. DC-Flüsse = Sollwert (ggf. auf NTC gekappt)
    """

    def __init__(self):
        self.codes = list(ZONES.keys())
        self.idx = {c: i for i, c in enumerate(self.codes)}
        self.n = len(self.codes)
        self.gen_shock: dict[str, dict[str, float]] = {}
        self.load_shock: dict[str, float] = {}
        self.line_derate: dict[tuple[str, str], float] = {}
        self.dc_setpoint: dict[tuple, float] = {}   # Override je DC-Kabel
        self.suscept_scale: dict[tuple[str, str], float] = {}  # Kalibrier-Faktoren
        self.zone_injection: dict[str, float] = {}  # Kalibrierung: unmodellierte MW
        self.ntc_override: dict[tuple, float] = {}   # Kalibrierung: empirische Limits
        self.freq_reference: dict[str, float] = {}   # Regel-MW je Zone im
        #   ungestörten Zustand (Basis für Δf; ohne Referenz gilt 0)
        #   Wenn A11 einen Fluss ÜBER der angenommenen NTC misst, ist die
        #   Annahme widerlegt – die Grenze kann nachweislich mehr. Kein Netz
        #   fährt dauerhaft >100%; gemessener Fluss ist eine Untergrenze der
        #   wahren Kapazität.
        #   (Kleinanlagen unter A75-Meldeschwelle + Austausch mit Nachbarn
        #    außerhalb des Modells; darf negativ sein, daher KEIN gen-Schock)

    # ── Schock-API (kompatibel zu v1) ─────────────────────────────────────────
    def reset_shocks(self):
        self.gen_shock.clear(); self.load_shock.clear()
        self.line_derate.clear(); self.dc_setpoint.clear()

    def shock_generation(self, zone, typ, delta_mw):
        self.gen_shock.setdefault(zone, {})[typ] = delta_mw

    def shock_load(self, zone, delta_mw):
        self.load_shock[zone] = delta_mw

    def shock_line(self, a, b, factor):
        """AC: Suszeptanz+NTC skalieren. DC: Sollwert skalieren (0 = Kabel aus)."""
        self.line_derate[(a, b)] = max(0.0, factor)

    def set_dc(self, a, b, mw, label=None):
        """DC-Sollwert setzen (z.B. aus A11-Messung). +mw = Fluss a→b."""
        self.dc_setpoint[(a, b, label)] = mw

    # ── intern ────────────────────────────────────────────────────────────────
    def _derate(self, ln: Line) -> float:
        """Nutzer-Drosselung (Leitungsschock). Skaliert Suszeptanz UND NTC:
        -50% heißt "einer von zwei Stromkreisen weg" – weniger Durchlass
        UND weniger Limit. Der alte Code skalierte nur die Suszeptanz;
        dadurch sah eine gedrosselte Leitung GESÜNDER aus (Fluss sank,
        Auslastung wurde aber gegen die volle NTC gemessen)."""
        return self.line_derate.get((ln.a, ln.b),
               self.line_derate.get((ln.b, ln.a), 1.0))

    def _cal(self, ln: Line) -> float:
        """A11-Kalibrierfaktor. Betrifft NUR die Suszeptanz (elektrische
        Verteilung), NIE die NTC – die Messung ändert das thermische
        Limit der Leitung nicht."""
        return self.suscept_scale.get((ln.a, ln.b),
               self.suscept_scale.get((ln.b, ln.a), 1.0))

    def _factor(self, ln: Line) -> float:
        return self._derate(ln) * self._cal(ln)

    def _dc_flow(self, ln: Line) -> float:
        sp = self.dc_setpoint.get((ln.a, ln.b, ln.label),
             self.dc_setpoint.get((ln.a, ln.b, None), ln.setpoint))
        d = self._derate(ln)
        sp *= d
        lim = ln.ntc * d
        return max(-lim, min(lim, sp))   # physisches Limit, mitgedrosselt

    def _effective_gen_load(self, c):
        z = ZONES[c]
        gen = dict(z.gen) if z.gen else {"_": z.base_gen}
        for typ, d in self.gen_shock.get(c, {}).items():
            gen[typ] = max(0.0, gen.get(typ, 0.0) + d)
        load = z.base_load + self.load_shock.get(c, 0.0)
        return gen, load

    def _islands(self) -> list[list[str]]:
        """
        Zusammenhangskomponenten über die WIRKSAMEN AC-Kanten.
        Normalfall: eine Komponente je Synchronzone. Kappt man aber z.B.
        die einzige AC-Verbindung des Baltikums (LitPol), zerfällt CE in
        zwei INSELN – und jede Insel muss sich fortan selbst ausregeln.
        Genau das ist elektrische Inselbildung; DC-Kabel verhindern sie
        nicht, denn sie koppeln nicht synchron.
        """
        parent = {c: c for c in self.codes}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
        for ln in INTERCONNECTORS:
            if ln.kind != "AC":
                continue
            if ln.suscept * self._factor(ln) < 1e-9:
                continue          # gekappte Leitung verbindet nicht
            union(ln.a, ln.b)
        groups: dict[str, list[str]] = {}
        for c in self.codes:
            groups.setdefault(find(c), []).append(c)
        return list(groups.values())

    def solve(self) -> dict:
        P_raw = np.zeros(self.n)
        cap = np.zeros(self.n)
        for c in self.codes:
            gen, load = self._effective_gen_load(c)
            P_raw[self.idx[c]] = (sum(gen.values()) - load
                                  + self.zone_injection.get(c, 0.0))
            cap[self.idx[c]] = sum(gen.values())

        # DC-Kabel: Sollwert als Injektion (Export beim Sender, Import beim Empfänger)
        dc_flows = {}
        for ln in INTERCONNECTORS:
            if ln.kind != "DC":
                continue
            f = self._dc_flow(ln)
            dc_flows[(ln.a, ln.b, ln.label)] = f
            P_raw[self.idx[ln.a]] -= f
            P_raw[self.idx[ln.b]] += f

        # Inseln bestimmen (dynamisch – Leitungsschocks können Zonen teilen!)
        islands = self._islands()
        island_of = {}
        for k, isl in enumerate(islands):
            for c in isl:
                island_of[c] = k

        # Verteilter Slack JE INSEL (jede Insel regelt sich selbst)
        P = P_raw.copy()
        reg = np.zeros(self.n)
        for isl in islands:
            ids = [self.idx[c] for c in isl]
            imb = P_raw[ids].sum()
            czap = cap[ids]
            alpha = czap / czap.sum() if czap.sum() else np.ones(len(ids)) / len(ids)
            for k, i in enumerate(ids):
                reg[i] = -alpha[k] * imb
                P[i] += reg[i]

        # AC-Lastfluss je Insel
        theta = np.zeros(self.n)
        for isl in islands:
            if len(isl) < 2:
                continue
            mi = {c: k for k, c in enumerate(isl)}
            m = len(isl)
            B = np.zeros((m, m))
            for ln in INTERCONNECTORS:
                if ln.kind != "AC":
                    continue
                if ln.a not in mi or ln.b not in mi:
                    continue
                b = ln.suscept * self._factor(ln)
                if b < 1e-9:
                    continue
                i, j = mi[ln.a], mi[ln.b]
                B[i, i] += b; B[j, j] += b; B[i, j] -= b; B[j, i] -= b
            keep = list(range(1, m))
            Pm = np.array([P[self.idx[c]] for c in isl])
            th = np.zeros(m)
            if keep:
                th[keep] = np.linalg.solve(B[np.ix_(keep, keep)], Pm[keep])
            for c in isl:
                theta[self.idx[c]] = th[mi[c]]

        # Kantenflüsse
        flows = []
        for ln in INTERCONNECTORS:
            if ln.kind == "AC":
                b = ln.suscept * self._factor(ln)
                f = b * (theta[self.idx[ln.a]] - theta[self.idx[ln.b]])
            else:
                f = dc_flows[(ln.a, ln.b, ln.label)]
            base_ntc = self.ntc_override.get((ln.a, ln.b, ln.label or None), ln.ntc)
            eff_ntc = base_ntc * self._derate(ln)
            util = abs(f) / eff_ntc if eff_ntc > 1e-9 else 0.0
            flows.append({
                "a": ln.a, "b": ln.b, "kind": ln.kind,
                "label": ln.label or None,
                "flow_mw": int(round(f)),
                "from": ln.a if f >= 0 else ln.b,
                "to":   ln.b if f >= 0 else ln.a,
                "abs_mw": int(round(abs(f))),
                "ntc": float(round(eff_ntc)),
                "ntc_base": float(base_ntc),
                "ntc_assumed": float(ln.ntc),
                "ntc_raised": bool(base_ntc > ln.ntc),
                "util": float(round(util, 3)),
                "overload": bool(util > 1.0),
            })

        zones_out = {}
        for c in self.codes:
            gen, load = self._effective_gen_load(c)
            g = sum(gen.values())
            phys = float(P[self.idx[c]])
            unmod = self.zone_injection.get(c, 0.0)
            zones_out[c] = {
                "gen_mw": int(round(g)), "load_mw": int(round(load)),
                "net_mw": int(round(g - load)),
                "unmodelled_mw": int(round(unmod)),
                "net_phys_mw": int(round(phys)),
                "reg_mw": int(round(reg[self.idx[c]])),
                "sync": ZONES[c].sync,
                "island": island_of[c],
                "position": ("EXPORT" if phys > 50 else
                             "IMPORT" if phys < -50 else "BALANCED"),
            }

        # Frequenz je Insel (quasistationär, relativ zur Referenz)
        sync_cap = {sz: sum(cap[self.idx[c]] for c in self.codes
                            if ZONES[c].sync == sz) or 1.0
                    for sz in SYNC_ZONES}
        frequencies = []
        for isl in islands:
            sync = ZONES[isl[0]].sync
            share = sum(cap[self.idx[c]] for c in isl) / sync_cap[sync]
            lam = FREQ_LAMBDA_MW_HZ[sync] * max(0.02, share)
            dreg = sum(reg[self.idx[c]] - self.freq_reference.get(c, 0.0)
                       for c in isl)
            hz = 50.0 - dreg / lam
            dev = (hz - 50.0) * 1000.0
            code, label = freq_status(dev)
            frequencies.append({
                "sync": sync,
                "members": sorted(isl),
                "is_island": True,   # unten: größte Komponente je Sync = Hauptnetz
                "hz": round(min(52.0, max(47.0, hz)), 3),   # Anzeige geklemmt
                "dev_mhz": int(round(dev)),
                "lambda_mw_hz": int(round(lam)),
                "status": code,
                "status_label": label,
            })
        # Größte Komponente je Synchronzone = "Hauptnetz", Rest = Inseln
        best: dict[str, dict] = {}
        for fq in frequencies:
            if fq["sync"] not in best or \
               len(fq["members"]) > len(best[fq["sync"]]["members"]):
                best[fq["sync"]] = fq
        for fq in best.values():
            fq["is_island"] = False
        frequencies.sort(key=lambda f: (f["sync"], f["is_island"],
                                        -len(f["members"])))

        overloaded = [f for f in flows if f["overload"]]
        # Bilanz je Synchronzone (muss je ~0 sein – inkl. DC-Austausch)
        sync_balance = {}
        for sz in SYNC_ZONES:
            ids = [self.idx[c] for c in self.codes if ZONES[c].sync == sz]
            sync_balance[sz] = int(round(P[ids].sum())) if ids else 0

        # Insel-Report: mehr Inseln als Synchronzonen = Netzauftrennung!
        island_report = None
        if len(islands) > len([s for s in SYNC_ZONES
                               if any(ZONES[c].sync == s for c in self.codes)]):
            island_report = [sorted(isl) for isl in
                             sorted(islands, key=len, reverse=True)]

        return {
            "n_islands": len(islands),
            "islands": island_report,
            "frequencies": frequencies,
            "flows": flows,
            "zones": zones_out,
            "overloads": overloaded,
            "n_overloads": len(overloaded),
            "max_util": float(round(max((f["util"] for f in flows), default=0), 3)),
            "sync_balance": sync_balance,
        }

    # ── ENTSO-E-Anbindung (unverändert nutzbar) ──────────────────────────────
    def set_from_entsoe(self, entsoe: dict, fuel_map: Optional[dict] = None):
        cat = fuel_map or _ENTSOE_TO_CAT
        for code, cd in entsoe.items():
            if code not in ZONES:
                continue
            z = ZONES[code]
            g = _mix()
            for typ, mw in (cd.get("generation") or {}).items():
                key = cat.get(typ, "other")
                g[key] = g.get(key, 0.0) + float(mw or 0)
            if any(g.values()):
                z.gen = g
                z.base_gen = sum(g.values())
            if cd.get("load_mw"):
                z.base_load = float(cd["load_mw"])


_ENTSOE_TO_CAT = {
    "Nuclear": "nuclear",
    "Fossil Hard Coal": "coal", "Fossil Brown Coal/Lignite": "coal",
    "Fossil Gas": "gas", "Fossil Oil": "gas", "Fossil Coal-derived Gas": "gas",
    "Fossil Peat": "coal", "Fossil Oil shale": "coal",
    "Hydro Run-of-river and poundage": "hydro", "Hydro Water Reservoir": "hydro",
    "Hydro Pumped Storage": "hydro",
    "Wind Onshore": "wind", "Wind Offshore": "wind",
    "Solar": "solar",
    "Biomass": "biomass",
    "Geothermal": "other", "Other renewable": "other", "Other": "other",
    "Waste": "other", "Marine": "other",
}


# ══════════════════════════════════════════════════════════════════════════════
# 4) N-1-STRESSTEST
# ══════════════════════════════════════════════════════════════════════════════

def n_minus_1(g: GridModel) -> dict:
    """
    Kappt jede Verbindung EINZELN (auf dem aktuellen Zustand inkl. aktiver
    Schocks und Kalibrierung) und bewertet die Folgen. Das ist die Rechnung,
    die Übertragungsnetzbetreiber laufend fahren: "Überlebt das Netz den
    Ausfall jedes einzelnen Elements?"

    Schweregrad je Ausfall:
      +1000  wenn das Netz in Inseln zerfällt (schwerste Folge)
      +10    je NEUER Überlastung
      +      Anstieg der max. Auslastung (in %-Punkten)
    """
    base = g.solve()
    results = []
    for ln in INTERCONNECTORS:
        key = (ln.a, ln.b)
        if g._derate(ln) < 1e-9:
            continue                      # bereits gekappt
        if ln.kind == "DC":
            # Label-genau kappen: parallele Kabel derselben Grenze (GB–IE:
            # EWIC + Moyle) fallen im N-1 EINZELN aus, nicht gemeinsam.
            saved_dc = dict(g.dc_setpoint)
            g.set_dc(ln.a, ln.b, 0.0, ln.label)
            try:
                r = g.solve()
            finally:
                g.dc_setpoint = saved_dc
        else:
            saved = dict(g.line_derate)
            g.line_derate[key] = 0.0
            try:
                r = g.solve()
            finally:
                g.line_derate = saved
        new_over = max(0, r["n_overloads"] - base["n_overloads"])
        split = r["n_islands"] > base["n_islands"]
        du = max(0.0, r["max_util"] - base["max_util"])
        worst = None
        if r["overloads"]:
            w = max(r["overloads"], key=lambda f: f["util"])
            worst = {"a": w["a"], "b": w["b"], "util": w["util"],
                     "abs_mw": w["abs_mw"], "ntc": w["ntc"]}
        results.append({
            "a": ln.a, "b": ln.b, "kind": ln.kind, "label": ln.label or None,
            "flow_base_mw": next(f["flow_mw"] for f in base["flows"]
                                 if f["a"] == ln.a and f["b"] == ln.b
                                 and f["label"] == (ln.label or None)),
            "island_split": bool(split),
            "n_islands": r["n_islands"],
            "new_overloads": int(new_over),
            "n_overloads": r["n_overloads"],
            "max_util": r["max_util"],
            "worst": worst,
            "severity": round((1000 if split else 0) + 10 * new_over
                              + 100 * du, 1),
        })
    results.sort(key=lambda x: -x["severity"])
    # "Kritisch" = strukturelle Folge (Inselbildung oder NEUE Überlastung).
    # Ein bloßer Anstieg der Auslastung fließt ins Ranking ein, macht einen
    # Ausfall aber nicht kritisch – sonst wäre jedes Netz "unsicher".
    critical = [r for r in results
                if r["island_split"] or r["new_overloads"] > 0]
    return {
        "base_overloads": base["n_overloads"],
        "base_max_util": base["max_util"],
        "n_tested": len(results),
        "n_critical": len(critical),
        "secure": len(critical) == 0,
        "ranking": results,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5) DEMO
# ══════════════════════════════════════════════════════════════════════════════

def _top_flows(res, n=10, kind=None):
    fl = [f for f in res["flows"] if kind is None or f["kind"] == kind]
    fl = sorted(fl, key=lambda f: f["util"], reverse=True)[:n]
    out = []
    for f in fl:
        tag = f" [{f['label']}]" if f["label"] else ""
        flag = "  ⚠" if f["overload"] else ""
        out.append(f"    {f['from']:>3}→{f['to']:<4}{f['kind']} {f['abs_mw']:>6} MW"
                   f"  ({f['util']*100:5.1f}%){tag}{flag}")
    return "\n".join(out)


if __name__ == "__main__":
    n_ac = sum(1 for l in INTERCONNECTORS if l.kind == "AC")
    n_dc = sum(1 for l in INTERCONNECTORS if l.kind == "DC")
    print("═" * 72)
    print("  MERIDIAN Grid v2  –  EU-Verbundnetz")
    print(f"  {len(ZONES)} Zonen | {n_ac} AC-Leitungen | {n_dc} HVDC-Kabel | "
          f"4 Synchronzonen")
    print("═" * 72)

    g = GridModel()
    base = g.solve()
    print(f"\n  BASISFALL: max {base['max_util']*100:.0f}% NTC, "
          f"{base['n_overloads']} Overloads")
    print(f"  Bilanz je Synchronzone: " +
          ", ".join(f"{k}={v:+d} MW" for k, v in base["sync_balance"].items()))
    print("\n  Meistbelastete AC-Grenzen:")
    print(_top_flows(base, 6, "AC"))
    print("\n  HVDC-Kabel (Sollwerte):")
    print(_top_flows(base, 6, "DC"))

    # Szenario: NordLink + NSL fallen aus → GB und CE verlieren NO-Wasserkraft
    print("\n" + "─" * 72)
    print("  SZENARIO: NordLink (DE–NO2) und North Sea Link (NO2–GB) fallen aus")
    print("─" * 72)
    g.reset_shocks()
    g.shock_line("DE", "NO2", 0.0)
    g.shock_line("NO2", "GB", 0.0)
    s = g.solve()
    for c in ("DE", "GB", "NO2"):
        b0, b1 = base["zones"][c], s["zones"][c]
        print(f"    {c:4} Regelbeitrag: {b0['reg_mw']:+6d} → {b1['reg_mw']:+6d} MW")
    print(f"    max. Auslastung {s['max_util']*100:.0f}% | "
          f"{s['n_overloads']} Overloads")
    print("\n  → Kernpunkt: Der Ausfall eines DC-Kabels verschiebt Erzeugung")
    print("    INNERHALB jeder Synchronzone (Regelleistung), aber der Strom")
    print("    kann NICHT über andere Wege zwischen den Zonen ausweichen –")
    print("    anders als bei AC-Ausfällen innerhalb einer Zone. Genau dieser")
    print("    Unterschied ist auf dem Nagelbrett der 'Draht mit Schalter'.")
