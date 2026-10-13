# gap_specs.json normalization (scripts/normalize_specs.py)

Regenerate + re-apply with `python3 scripts/normalize_specs.py` (idempotent).

## Encoding convention

- `status` is plain ASCII: one of `planned`, `done`, `partial`.
- `priority` is a separate field: `""`, `low`, `medium`, `high`, `critical`.
- `version` is the em-dash placeholder or a dotted version.

## status values normalized -> planned/done/partial


## priority extracted out of status


## version values reset to the em-dash placeholder


## cross-domain category contamination

335 categories appear in more than one domain; the full map is in `planned/CATEGORY_CONTAMINATION.tsv`.

REMOVED from `domain=programming_language` (they are application content whose natural domains already exist), recorded verbatim:

| domain | category | module | status | notes |
|---|---|---|---|---|

(0 specs removed.)

KEPT under `programming_language`: Audio, Video, Robotics, DL, Encryption, TLS, Hashing, Key Mgmt, PKI, Protocol, OS, Compiler, VM, Numerical, Serialization, CPU and the rest -- these are stdlib capability areas and several are exercised by gate rows in EXPECTED_STDLIB.tsv (programming_language_dl_*, _tls_*, _encryption_*, ...).

## exact duplicate specs (recorded, not dropped)

- accounting/Compliance/Federal
- accounting/Compliance/State
- accounting/Compliance/SOX
- advertising/Measurement/Analytics
- advertising/Pricing/Strategy
- advertising/Customer/Experience
- advertising/Customer/Loyalty
- advertising/Product/Testing
- advertising/Data/Visualization
- airlines/Network/Route
- airlines/Network/Hub
- airlines/Operations/Ground
- airlines/Operations/Ground
- airlines/Sustainability/Carbon
- airlines/Digital/Analytics
- airlines/Digital/IoT
- airlines/Digital/AI
- airlines/Digital/Digital Twin
- cannabis/Products/Flower
- cannabis/Products/Edible
- cannabis/Products/Topical
- chemicals_industry/Construction/Waterproofing
- countries/Region/São Tomé & Príncipe
- countries/Region/Equatorial Guinea
- countries/Region/Gabon
- countries/Region/Republic of Congo
- countries/Region/DRC
- countries/Region/Angola
- countries/Region/Namibia
- countries/Region/Botswana
- countries/Region/Zimbabwe
- countries/Region/Zambia
- countries/Region/Mozambique
- countries/Region/Malawi
- countries/Region/Tanzania
- countries/Region/Kenya
- countries/Region/Uganda
- countries/Region/Rwanda
- countries/Region/Burundi
- countries/Region/Ethiopia
- countries/Region/Eritrea
- countries/Region/Djibouti
- countries/Region/Somalia
- countries/Region/South Sudan
- countries/Region/Sudan
- countries/Region/Chad
- countries/Region/Niger
- countries/Region/Mali
- countries/Region/Burkina Faso
- countries/Region/Mauritania
- countries/Region/Senegal
- countries/Region/Gambia
- countries/Region/Guinea-Bissau
- countries/Region/Guinea
- countries/Region/Sierra Leone
- countries/Region/Liberia
- countries/Region/Ivory Coast
- countries/Region/Ghana
- countries/Region/Togo
- countries/Region/Benin
- countries/Region/Nigeria
- countries/Region/Cameroon
- countries/Region/Central African Republic
- electronics/Display/LCD
- electronics/Display/OLED
- energy/Electrical/Generator
- energy/Electrical/Transformer
- energy/Operations/SCADA
- energy/Storage/Thermal
- entertainment/Genre/Action
- entertainment/Genre/Horror
- insurance/Actuarial/Pricing
- insurance/Actuarial/Reserving
- insurance/Actuarial/Reinsurance
- insurance/Compliance/State
- insurance/Compliance/Federal
- insurance_industry/Actuarial/Pricing
- insurance_industry/Actuarial/Reserving
- insurance_industry/Actuarial/Reinsurance
- insurance_industry/Claims/Property
- insurance_industry/Claims/Casualty
- insurance_industry/Claims/Litigation
- insurance_industry/Actuarial/Pricing
- insurance_industry/Actuarial/Reserving
- insurance_industry/Actuarial/Reinsurance
- insurance_industry/Compliance/State
- insurance_industry/Commercial/Property
- insurance_industry/Commercial/Professional
- insurance_industry/Commercial/Marine
- insurance_industry/Commercial/Surety
- insurance_industry/Personal/Auto
- insurance_industry/Personal/Umbrella
- insurance_industry/Claims/Litigation
- insurance_industry/Distribution/Digital
- insurance_industry/Analytics/Predictive
- insurance_industry/Analytics/Telematics
- insurance_industry/Analytics/Cat Modeling
- insurance_industry/Analytics/ESG
- investment/Fixed Income/Government
- investment/Fixed Income/Corporate
- investment/Fixed Income/Securitized
- investment/Fixed Income/Municipal
- investment/Derivatives/Futures
- investment/Derivatives/Options
- investment/Derivatives/Swaps
- investment/Execution/Venue
- investment/Advisory/Strategic
- investment/Advisory/Financial
- investment/Advisory/Valuation
- investment/Advisory/Fairness
- investment/Advisory/Solvency
- investment/Advisory/ESOP
- investment/Advisory/409A
- investment/Advisory/Purchase Price
- investment/Advisory/Transfer Pricing
- investment/Advisory/Tax
- investment/Advisory/Regulatory
- investment/Advisory/ESG
- investment/Advisory/Climate
- investment/Advisory/Social
- investment/Advisory/Governance
- investment/Advisory/Cyber
- investment/Advisory/Reputational
- maritime/Offshore/Subsea
- pharmaceuticals/Biologics/Vaccine
- pharmaceuticals/Biologics/Cell Therapy
- pharmaceuticals/Biologics/Gene Therapy
- pharmaceuticals/Biologics/Biosimilar
- programming_language/Embedded/RTOS
- programming_language/Robotics/Control
- programming_language/Robotics/Manipulation
- programming_language/Robotics/Navigation
- programming_language/Consensus/PoW
- programming_language/Consensus/PoS
- psychedelics/Therapy/Addiction
- psychedelics/Protocol/Preparation
- psychedelics/Protocol/Session
- psychedelics/Protocol/Integration
- psychedelics/Protocol/Dosing
- psychedelics/Therapy/Depression
- psychedelics/Therapy/Anxiety
- real_estate/Valuation/AVM
- religious_orgs/Hindu/Temple
- religious_orgs/Sikh/Gurdwara
- renewable_energy/Electrical/Generator
- tobacco/Regulation/FDA
- tobacco/Distribution/Wholesale
- tobacco/Distribution/Retail
- tobacco/Distribution/Online
- tobacco/Marketing/Trade
- tobacco/Marketing/Consumer
- tobacco/Quality/Chemical
- tobacco/Quality/Physical
- tobacco/Quality/Microbial
- tobacco/Regulation/FDA
- tobacco/Regulation/TPD
- tobacco/Regulation/State
- tobacco/Regulation/Local
- tobacco/Distribution/Wholesale
- tobacco/Distribution/Retail
- tobacco/Distribution/Online
- tobacco/Marketing/Trade
- tobacco/Marketing/Consumer
- tobacco/Manufacturing/Fermentation
- tobacco/Quality/Physical
- tobacco/Quality/Chemical
- tobacco/Quality/Microbial
- tobacco/Regulation/FDA
- tobacco/Regulation/TPD
- tobacco/Regulation/State
- tobacco/Regulation/Local
- tobacco/Distribution/Wholesale
- tobacco/Distribution/Retail
- tobacco/Distribution/Online
- tobacco/Marketing/Trade
- tobacco/Marketing/Consumer
- tobacco/Marketing/Point-of-Sale
- transportation/Freight/Intermodal
- trucking/Technology/TMS
- trucking/Technology/Analytics
- venture_capital/Fundraising/LP Relations
- venture_capital/Fundraising/Closing
- venture_capital/Fundraising/Terms
- venture_capital/Sourcing/Deal Flow
- venture_capital/Sourcing/Screening
- venture_capital/Due Diligence/Financial
- venture_capital/Due Diligence/Legal
- venture_capital/Valuation/Methods
- venture_capital/Valuation/Terms
- venture_capital/Exit/IPO
- venture_capital/Exit/M&A
- venture_capital/Exit/Secondary
- venture_capital/Sourcing/Deal Flow
- venture_capital/Sourcing/Screening
- venture_capital/Due Diligence/Market
- venture_capital/Due Diligence/Team
- venture_capital/Valuation/Methods
- venture_capital/Valuation/Terms
- venture_capital/Investment/Seed
- venture_capital/Portfolio/Management
- venture_capital/Portfolio/Value Add
- venture_capital/Exit/IPO
- venture_capital/Exit/M&A
- venture_capital/Exit/Secondary

