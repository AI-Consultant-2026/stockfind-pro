"""
Universe definition for the StockFind Pro simulated data layer.

Every ticker is fictional (to avoid asserting real facts about real companies)
but is tagged with an "archetype" that drives how its price and fundamentals
are generated, so that each of the ten opportunity strategies has genuine,
discoverable examples in the simulated universe — plus deliberate "trap"
archetypes (value traps, deteriorating fundamentals) so the system proves it
can tell a real opportunity apart from a stock that merely looks similar on
one dimension.

Swap this module (or the DB it seeds) for a real data feed later — nothing
above the data_providers layer needs to change.
"""

SECTORS = {
    "Technology": ["Software", "Semiconductors", "Hardware", "Cloud Services"],
    "Healthcare": ["Biotechnology", "Pharmaceuticals", "Medical Devices", "Health Services"],
    "Energy": ["Oil & Gas", "Renewables", "Energy Services"],
    "Financials": ["Banks", "Insurance", "Asset Management"],
    "Consumer": ["Retail", "Consumer Staples", "Restaurants", "Apparel"],
    "Utilities": ["Electric Utilities", "Water Utilities"],
    "Industrials": ["Aerospace & Defense", "Machinery", "Transportation"],
    "Communication Services": ["Media", "Telecom", "Internet"],
}

# archetype -> narrative used by generator to shape price/fundamental trajectories
ARCHETYPES = [
    "compounder",               # steady high-quality growth, grinds higher
    "momentum_breakout",        # recent consolidation -> breakout on volume
    "earnings_momentum",        # beats + raised guidance + estimate revisions up
    "fallen_angel_good",        # down 30-45% but fundamentals still healthy
    "fallen_angel_bad",         # down big AND fundamentals deteriorating (value trap)
    "undervalued_quality",      # strong quality/balance sheet, cheap multiple
    "institutional_accumulation",
    "insider_accumulation",
    "short_squeeze",            # high short interest, volatile upside spike
    "mean_reversion_healthy",   # sharp short-term pullback, fundamentals fine
    "mean_reversion_unhealthy", # sharp pullback, business genuinely deteriorating
    "deteriorating",            # steady fundamental decline, downtrend, risk warning
    "generic_neutral",          # unremarkable, fills out the universe
]

# (ticker, name, sector, industry, archetype)
UNIVERSE = [
    ("NVX",  "Novantix Corp",          "Technology", "Semiconductors", "earnings_momentum"),
    ("QBIT", "Qubitron Systems",       "Technology", "Semiconductors", "momentum_breakout"),
    ("CLDF",  "CloudForge Inc",        "Technology", "Cloud Services", "compounder"),
    ("SFTW", "Softwerx Corp",          "Technology", "Software", "undervalued_quality"),
    ("HRZN", "Horizon Data Systems",   "Technology", "Software", "institutional_accumulation"),
    ("PXLR", "Pixelara Technologies",  "Technology", "Hardware", "short_squeeze"),
    ("NEXG", "NexGen Chips",           "Technology", "Semiconductors", "fallen_angel_good"),
    ("VLTC", "Voltcore Devices",       "Technology", "Hardware", "deteriorating"),
    ("APXS", "Apex Software Solutions","Technology", "Software", "insider_accumulation"),
    ("DTAS", "DataStream Analytics",   "Technology", "Cloud Services", "mean_reversion_healthy"),
    ("SYNC", "SyncWave Networks",      "Technology", "Hardware", "generic_neutral"),
    ("ORBT", "Orbital Compute",        "Technology", "Cloud Services", "momentum_breakout"),

    ("GNTX", "Genethera Biosciences",  "Healthcare", "Biotechnology", "earnings_momentum"),
    ("MEDL", "Medlogic Devices",       "Healthcare", "Medical Devices", "compounder"),
    ("PHRX", "PharmaCrest Inc",        "Healthcare", "Pharmaceuticals", "fallen_angel_good"),
    ("VITA", "VitaHealth Group",       "Healthcare", "Health Services", "undervalued_quality"),
    ("CURX", "Curaxis Therapeutics",   "Healthcare", "Biotechnology", "short_squeeze"),
    ("BIOM", "Biomerix Labs",          "Healthcare", "Biotechnology", "mean_reversion_unhealthy"),
    ("ONCG", "Oncogenix Pharma",       "Healthcare", "Pharmaceuticals", "insider_accumulation"),
    ("SERN", "Serenity Health",        "Healthcare", "Health Services", "deteriorating"),
    ("IMMX", "Immunexa Bio",           "Healthcare", "Biotechnology", "institutional_accumulation"),
    ("DVMD", "DeviceMed Corp",         "Healthcare", "Medical Devices", "generic_neutral"),

    ("PTRX", "Petrona Resources",      "Energy", "Oil & Gas", "fallen_angel_bad"),
    ("SLRW", "SolaraWatt Energy",      "Energy", "Renewables", "momentum_breakout"),
    ("HYDG", "HydroGen Power",         "Energy", "Renewables", "earnings_momentum"),
    ("DRXE", "Drexel Energy Corp",     "Energy", "Oil & Gas", "deteriorating"),
    ("WNDF", "WindField Holdings",     "Energy", "Renewables", "undervalued_quality"),
    ("APEX",  "ApexDrill Services",    "Energy", "Energy Services", "generic_neutral"),
    ("CBNE",  "CarbonEdge Ltd",        "Energy", "Energy Services", "mean_reversion_healthy"),

    ("FDBK", "FideliBank Corp",        "Financials", "Banks", "undervalued_quality"),
    ("STCP", "SterlingCapital Group",  "Financials", "Asset Management", "compounder"),
    ("ASRN",  "AssureNorth Insurance", "Financials", "Insurance", "institutional_accumulation"),
    ("MRDN", "Meridian Trust Bank",    "Financials", "Banks", "fallen_angel_good"),
    ("QNTM",  "Quantum Capital Corp",  "Financials", "Asset Management", "insider_accumulation"),
    ("LGCB",  "LegacyBanc Inc",        "Financials", "Banks", "deteriorating"),
    ("PRSH",  "Parashield Insurance",  "Financials", "Insurance", "generic_neutral"),

    ("BRTL", "Brantley Retail Co",     "Consumer", "Retail", "momentum_breakout"),
    ("SVRY", "Savory Brands Inc",      "Consumer", "Restaurants", "earnings_momentum"),
    ("NRTH",  "NorthStar Apparel",     "Consumer", "Apparel", "fallen_angel_good"),
    ("PMRY",  "PrimaryGoods Co",       "Consumer", "Consumer Staples", "compounder"),
    ("URBN2", "UrbanNest Retail",      "Consumer", "Retail", "short_squeeze"),
    ("FRSH",  "FreshHarvest Foods",    "Consumer", "Consumer Staples", "undervalued_quality"),
    ("TRND",  "TrendLine Apparel",     "Consumer", "Apparel", "mean_reversion_unhealthy"),
    ("DINE",  "DineWorks Group",       "Consumer", "Restaurants", "deteriorating"),
    ("GLDS",  "GoldenState Retail",    "Consumer", "Retail", "generic_neutral"),

    ("VOLT",  "VoltGrid Utilities",    "Utilities", "Electric Utilities", "compounder"),
    ("AQPR",  "AquaPure Water Co",     "Utilities", "Water Utilities", "undervalued_quality"),
    ("CVLT",  "CivicLight Power",      "Utilities", "Electric Utilities", "generic_neutral"),
    ("STRM",  "StreamWater Corp",      "Utilities", "Water Utilities", "institutional_accumulation"),

    ("AERX",  "AeroDyne Defense",      "Industrials", "Aerospace & Defense", "earnings_momentum"),
    ("MTRX2", "MatrixWorks Industrial","Industrials", "Machinery", "compounder"),
    ("SKYF",  "SkyFreight Logistics",  "Industrials", "Transportation", "momentum_breakout"),
    ("IRNW",  "IronWorks Machinery",   "Industrials", "Machinery", "fallen_angel_bad"),
    ("TRLNS", "TransLines Corp",       "Industrials", "Transportation", "mean_reversion_healthy"),
    ("DFNS",  "DefensaTech Systems",   "Industrials", "Aerospace & Defense", "insider_accumulation"),
    ("BLDR2", "BuilderCore Industrial","Industrials", "Machinery", "generic_neutral"),

    ("MDSTR", "MediaStar Group",       "Communication Services", "Media", "fallen_angel_good"),
    ("TELX",  "TelXNet Communications","Communication Services", "Telecom", "undervalued_quality"),
    ("NETV",  "NetVista Inc",          "Communication Services", "Internet", "momentum_breakout"),
    ("STRC",  "StreamCast Media",      "Communication Services", "Media", "short_squeeze"),
    ("CNCT",  "ConnectSphere Telecom", "Communication Services", "Telecom", "deteriorating"),
    ("WVLN",  "WaveLink Internet",     "Communication Services", "Internet", "institutional_accumulation"),
    ("BCST",  "Broadcastia Ltd",       "Communication Services", "Media", "generic_neutral"),
]

assert len({t[0] for t in UNIVERSE}) == len(UNIVERSE), "duplicate tickers in universe"
