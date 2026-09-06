# Electric & Gas Utilities — Roadmap

## What Quanta must support: power generation, transmission, distribution, natural gas, and utility operations.

---

## Power Generation

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Thermal | Coal | 🔲 planned | — | — | Pulverized, fluidized, IGCC, CFB |
| Thermal | Gas | 🔲 planned | — | — | CCGT, OCGT, CHP, simple, reheat |
| Thermal | Oil | 🔲 planned | — | — | Residual, distillate, peaking, backup |
| Nuclear | PWR | 🔲 planned | — | — | Pressurized water, Westinghouse, AREVA |
| Nuclear | BWR | 🔲 planned | — | — | Boiling water, GE-Hitachi |
| Nuclear | SMR | 🔲 planned | — | — | NuScale, BWRX-300, microreactor |
| Renewable | Solar | 🔲 planned | — | — | PV, CSP, floating, agrivoltaic |
| Renewable | Wind | 🔲 planned | — | — | Onshore, offshore, floating |
| Renewable | Hydro | 🔲 planned | — | — | Dam, run-of-river, pumped storage |
| Renewable | Biomass | 🔲 planned | — | — | Direct, biogas, co-fire, gasification |
| Renewable | Geothermal | 🔲 planned | — | — | Flash, binary, dry steam |
| Storage | Battery | 🔲 planned | — | — | Li-ion, flow, sodium, compressed air |
| Storage | Pumped Hydro | 🔲 planned | — | — | Closed-loop, open-loop, variable speed |

---

## Transmission

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| HVAC | Overhead | 🔲 planned | — | — | AC, 69-765 kV, tower, conductor |
| HVAC | Underground | 🔲 planned | — | — | Cable, XLPE, oil-filled, pipe-type |
| HVAC | Substation | 🔲 planned | — | — | Step-up, step-down, switching, GIS |
| HVDC | LCC | 🔲 planned | — | — | Line-commutated, 12-pulse, converter |
| HVDC | VSC | 🔲 planned | — | — | Voltage-source, MMC, HVDC Light |
| HVDC | Cable | 🔲 planned | — | — | Submarine, underground, overhead |
| FACTS | SVC | 🔲 planned | — | — | Static VAR compensator, TCR, TSC |
| FACTS | STATCOM | 🔲 planned | — | — | Static compensator, voltage-source |
| FACTS | TCSC | 🔲 planned | — | — | Thyristor-controlled series capacitor |
| FACTS | UPFC | 🔲 planned | — | — | Unified power flow controller |
| Grid | Interconnection | 🔲 planned | — | — | Regional, national, international |
| Grid | Synchronous | 🔲 planned | — | — | Condenser, inertia, frequency |
| Grid | Microgrid | 🔲 planned | — | — | Island, grid-connected, controller |

---

## Distribution

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Network | Feeder | 🔲 planned | — | — | Overhead, underground, recloser |
| Network | Substation | 🔲 planned | — | — | Step-down, switchgear, protection |
| Network | Transformer | 🔲 planned | — | — | Pad-mounted, pole-mounted, vault |
| Network | DER | 🔲 planned | — | — | Solar, storage, EV, demand response |
| Network | Microgrid | 🔲 planned | — | — | Island, grid-connected, controller |
| Network | Voltage | 🔲 planned | — | — | Regulation, VAR, power factor |
| Protection | Relay | 🔲 planned | — | — | Overcurrent, distance, differential |
| Protection | Coordination | 🔲 planned | — | — | TCC, fuse, recloser, sectionalizer |
| Metering | AMI | 🔲 planned | — | — | Smart, AMR, MDMS, communication |
| Metering | Prepay | 🔲 planned | — | — | Token, card, mobile, smart |
| Metering | Net | 🔲 planned | — | — | Bi-directional, feed-in, TOU |
| Automation | SCADA | 🔲 planned | — | — | Monitoring, control, historian |
| Automation | DMS | 🔲 planned | — | — | Outage, Volt-VAR, FLISR, DERMS |
| Automation | OMS | 🔲 planned | — | — | Outage, crew, restoration, SAIDI |
| Automation | DERMS | 🔲 planned | — | — | Solar, storage, EV, flexibility |

---

## Natural Gas

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Upstream | Production | 🔲 planned | — | — | Conventional, shale, tight, CBM |
| Upstream | Processing | 🔲 planned | — | — | Separation, dehydration, treating |
| Upstream | Gathering | 🔲 planned | — | — | Pipeline, compression, processing |
| Midstream | Transmission | 🔲 planned | — | — | Pipeline, compression, storage |
| Midstream | LNG | 🔲 planned | — | — | Liquefaction, shipping, regasification |
| Midstream | Storage | 🔲 planned | — | — | Depleted reservoir, aquifer, salt cavern |
| Midstream | Gathering | 🔲 planned | — | — | Pipeline, processing, compression |
| Downstream | Distribution | 🔲 planned | — | — | City gate, regulator, meter, customer |
| Downstream | LDC | 🔲 planned | — | — | Local distribution company, tariff |
| Downstream | Marketer | 🔲 planned | — | — | Supplier, aggregator, broker |
| Trading | Physical | 🔲 planned | — | — | Spot, forward, basis, index |
| Trading | Financial | 🔲 planned | — | — | Futures, options, swaps, spreads |
| Trading | Capacity | 🔲 planned | — | — | Release, recall, interruptible, firm |
| Safety | Integrity | 🔲 planned | — | — | Assessment, inspection, repair, prevention |
| Safety | Leak | 🔲 planned | — | — | Detection, survey, repair, prevention |
| Safety | Emergency | 🔲 planned | — | — | Response, evacuation, investigation |
| Environmental | Air | 🔲 planned | — | — | Emissions, LDAR, flare, vent |
| Environmental | Water | 🔲 planned | — | — | Discharge, treatment, SPCC, storm |
| Environmental | Waste | 🔲 planned | — | — | Characterization, disposal, remediation |

---

## Utility Operations

| Category | Module | Status | Version | Stdlib | Notes |
|----------|--------|--------|---------|--------|-------|
| Markets | Wholesale | 🔲 planned | — | — | Day-ahead, real-time, capacity, ancillary |
| Markets | Retail | 🔲 planned | — | — | Rate design, TOU, demand charge, net |
| Markets | Carbon | 🔲 planned | — | — | Cap-and-trade, REC, carbon credit |
| Markets | Capacity | 🔲 planned | — | — | Auction, bilateral, must-offer |
| Markets | Ancillary | 🔲 planned | — | — | Frequency, spinning, non-spinning, regulation |
| Regulation | State | 🔲 planned | — | — | PUC, rate case, rate base, ROE |
| Regulation | Federal | 🔲 planned | — | — | FERC, NERC, EPA, PHMSA |
| Regulation | Local | 🔲 planned | — | — | Municipal, cooperative, franchise |
| Planning | IRP | 🔲 planned | — | — | Integrated resource plan, scenario |
| Planning | Transmission | 🔲 planned | — | — | Regional, interconnection, upgrade |
| Planning | Distribution | 🔲 planned | — | — | Capacity, reliability, resilience, DER |
| Planning | DER | 🔲 planned | — | — | Hosting capacity, flexibility, market |
| Finance | Rate | 🔲 planned | — | — | Base, fuel, riders, decoupling, trackers |
| Finance | Capital | 🔲 planned | — | — | Project, debt, equity, AFUDC, CWIP |
| Finance | Accounting | 🔲 planned | — | — | Regulatory, GAAP, tax, depreciation |
| Finance | Risk | 🔲 planned | — | — | Market, credit, operational, regulatory |
| Customer | Billing | 🔲 planned | — | — | Meter, rate, tax, deposit, collection |
| Customer | Service | 🔲 planned | — | — | Connection, disconnection, move, name |
| Customer | Programs | 🔲 planned | — | — | EE, DR, DG, EV, low-income |
| Customer | Communication | 🔲 planned | — | — | Web, app, IVR, chat, social |
| Work | Management | 🔲 planned | — | — | Work order, crew, asset, inventory |
| Work | Safety | 🔲 planned | — | — | PPE, lockout, confined, fall, arc |
| Work | Vegetation | 🔲 planned | — | — | Inspection, trimming, removal, herbicide |
| Asset | Management | 🔲 planned | — | — | Strategy, condition, risk, lifecycle |
| Asset | Performance | 🔲 planned | — | — | SAIDI, SAIFI, CAIDI, MAIFI, reliability |
| Asset | Condition | 🔲 planned | — | — | Assessment, testing, monitoring, diagnosis |
| Asset | Replacement | 🔲 planned | — | — | Prioritization, planning, execution |
| Cyber | Security | 🔲 planned | — | — | NERC CIP, zero trust, OT security |
| Cyber | Privacy | 🔲 planned | — | — | Customer, employee, smart meter, GDPR |
| Cyber | Resilience | 🔲 planned | — | — | Backup, recovery, incident, BCP |
| ESG | Reporting | 🔲 planned | — | — | SASB, GRI, TCFD, CDP, integrated |
| ESG | Climate | 🔲 planned | — | — | Carbon, TCFD, net-zero, scenario |
| ESG | Social | 🔲 planned | — | — | Diversity, equity, inclusion, community |
| ESG | Governance | 🔲 planned | — | — | Board, compensation, transparency |
