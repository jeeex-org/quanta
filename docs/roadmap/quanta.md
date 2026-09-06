# Quanta — Language Core Roadmap

## The Quanta programming language itself.

**Single source of truth for Quanta's own implementation.** All other capabilities live in domain roadmaps.

---

## Self-Improvement Prerequisites

Quanta can only self-improve when its core subsystems are in place. These are the **hard prerequisites** before the self-improvement loop (read roadmap → generate code → test → merge) can run:

| SI Component | Prerequisite | Quanta Module | Status |
|---|---|---|---|
| Spec Parser | stdlib I/O + markdown parser | `std/io` + `std/regex` | ✅ |
| Spec-to-IR mapper | IR + type system stable | `std/ir` + `std/types` | ✅ |
| Code synthesizer | Pattern library + codegen | `std/patterns` + `std/codegen` | ✅ |
| Quanta emitter | Compiler + AST + printer | `compiler` + `std/ast` + `std/print` | ✅ |
| Test generator | Test harness + EXPECTED.tsv | `std/testing` + `test/` | ✅ |
| Merge automation | Git integration + CI | `std/git` + `std/ci` | ✅ |

These must be built **before** SI can read its own gaps and fill them. Each SI component is itself a Quanta module listed in the domains roadmap.

---

## Domains

Quanta's domain roadmaps cover every industry, academic discipline, and general topic. Each domain file lists modules (what Quanta must implement) with status: ✅ done or 🔲 planned.

| Domain | Modules | Done | Planned |
|--------|---------|------|---------|
| [programming_language](domains/programming_language.md) | 400+ | 30 | 370+ |
| [mathematics](domains/mathematics.md) | 54 | 4 | 50 |
| [physics](domains/physics.md) | 65 | 0 | 65 |
| [chemistry](domains/chemistry.md) | 68 | 0 | 68 |
| [biology](domains/biology.md) | 95 | 0 | 95 |
| [computer_science](domains/computer_science.md) | 45 | 0 | 45 |
| [medicine](domains/medicine.md) | 50+ | 0 | 50+ |
| [engineering](domains/engineering.md) | 100+ | 0 | 100+ |
| [finance](domains/finance.md) | 80+ | 0 | 80+ |
| [law](domains/law.md) | 90+ | 0 | 90+ |
| [education](domains/education.md) | 80+ | 0 | 80+ |
| [agriculture](domains/agriculture.md) | 90+ | 0 | 90+ |
| [energy](domains/energy.md) | 90+ | 0 | 90+ |
| [manufacturing](domains/manufacturing.md) | 100+ | 0 | 100+ |
| [construction](domains/construction.md) | 90+ | 0 | 90+ |
| [transportation](domains/transportation.md) | 90+ | 0 | 90+ |
| [defense](domains/defense.md) | 100+ | 0 | 100+ |
| [government](domains/government.md) | 50+ | 0 | 50+ |
| [real_estate](domains/real_estate.md) | 40+ | 0 | 40+ |
| [retail](domains/retail.md) | 40+ | 0 | 40+ |
| [entertainment](domains/entertainment.md) | 50+ | 0 | 50+ |
| [telecommunications](domains/telecommunications.md) | 40+ | 0 | 40+ |
| [mining](domains/mining.md) | 40+ | 0 | 40+ |
| [pharmaceuticals](domains/pharmaceuticals.md) | 50+ | 0 | 50+ |
| [hospitality](domains/hospitality.md) | 40+ | 0 | 40+ |
| [insurance](domains/insurance.md) | 40+ | 0 | 40+ |
| [consulting](domains/consulting.md) | 40+ | 0 | 40+ |
| [nonprofit](domains/nonprofit.md) | 30+ | 0 | 30+ |
| [religious_orgs](domains/religious_orgs.md) | 30+ | 0 | 30+ |
| [waste_management](domains/waste_management.md) | 30+ | 0 | 30+ |
| [water_utilities](domains/water_utilities.md) | 30+ | 0 | 30+ |
| [forestry](domains/forestry.md) | 40+ | 0 | 40+ |
| [fishing](domains/fishing.md) | 30+ | 0 | 30+ |
| [food_beverage](domains/food_beverage.md) | 50+ | 0 | 50+ |
| [tobacco](domains/tobacco.md) | 30+ | 0 | 30+ |
| [logistics](domains/logistics.md) | 50+ | 0 | 50+ |
| [advertising](domains/advertising.md) | 40+ | 0 | 40+ |
| [media](domains/media.md) | 40+ | 0 | 40+ |
| [other_services](domains/other_services.md) | 40+ | 0 | 40+ |
| [admin_support](domains/admin_support.md) | 30+ | 0 | 30+ |
| [information](domains/information.md) | 40+ | 0 | 40+ |
| [wholesale](domains/wholesale.md) | 40+ | 0 | 40+ |
| [automotive](domains/automotive.md) | 40+ | 0 | 40+ |
| [maritime](domains/maritime.md) | 40+ | 0 | 40+ |
| [renewable_energy](domains/renewable_energy.md) | 40+ | 0 | 40+ |
| [utilities](domains/utilities.md) | 40+ | 0 | 40+ |
| [trucking](domains/trucking.md) | 40+ | 0 | 40+ |
| [real_estate_construction](domains/real_estate_construction.md) | 40+ | 0 | 40+ |
| [insurance_industry](domains/insurance_industry.md) | 40+ | 0 | 40+ |
| [investment](domains/investment.md) | 40+ | 0 | 40+ |
| [chemicals_industry](domains/chemicals_industry.md) | 40+ | 0 | 40+ |
| [electronics](domains/electronics.md) | 40+ | 0 | 40+ |
| [aerospace](domains/aerospace.md) | 40+ | 0 | 40+ |
| [textiles](domains/textiles.md) | 40+ | 0 | 40+ |
| [venture_capital](domains/venture_capital.md) | 40+ | 0 | 40+ |
| [accounting](domains/accounting.md) | 40+ | 0 | 40+ |
| [healthcare_industry](domains/healthcare_industry.md) | 50+ | 0 | 50+ |
| [pharmaceutical_industry](domains/pharmaceutical_industry.md) | 50+ | 0 | 50+ |
| [biotechnology_industry](domains/biotechnology_industry.md) | 50+ | 0 | 50+ |
| [nanotechnology](domains/nanotechnology.md) | 40+ | 0 | 40+ |
| [robotics_industry](domains/robotics_industry.md) | 50+ | 0 | 50+ |
| [artificial_intelligence_industry](domains/artificial_intelligence_industry.md) | 60+ | 0 | 60+ |
| [cybersecurity_industry](domains/cybersecurity_industry.md) | 50+ | 0 | 50+ |
| [blockchain_industry](domains/blockchain_industry.md) | 40+ | 0 | 40+ |
| [gaming_industry](domains/gaming_industry.md) | 50+ | 0 | 50+ |
| [entertainment_industry](domains/entertainment_industry.md) | 50+ | 0 | 50+ |
| [sports_industry](domains/sports_industry.md) | 50+ | 0 | 50+ |
| [tourism_industry](domains/tourism_industry.md) | 40+ | 0 | 40+ |
| [legal_industry](domains/legal_industry.md) | 40+ | 0 | 40+ |
| [consulting_industry](domains/consulting_industry.md) | 40+ | 0 | 40+ |
| [space](domains/space.md) | 48 | 0 | 48 |
| [veterinary](domains/veterinary.md) | 39 | 0 | 39 |
| [dentistry](domains/dentistry.md) | 40 | 0 | 40 |
| [optometry](domains/optometry.md) | 45 | 0 | 45 |
| [mental_health](domains/mental_health.md) | 48 | 0 | 48 |
| [rehabilitation](domains/rehabilitation.md) | 56 | 0 | 56 |
| [nutrition](domains/nutrition.md) | 47 | 0 | 47 |
| [pharmacy_retail](domains/pharmacy_retail.md) | 47 | 0 | 47 |
| [medical_devices](domains/medical_devices.md) | 48 | 0 | 48 |
| [biotechnology](domains/biotechnology.md) | 48 | 0 | 48 |
| [nanotechnology](domains/nanotechnology.md) | 48 | 0 | 48 |
| [quantum_computing](domains/quantum_computing.md) | 61 | 0 | 61 |
| [robotics](domains/robotics.md) | 40+ | 0 | 40+ |
| [drones](domains/drones.md) | 40+ | 0 | 40+ |
| [virtual_reality](domains/virtual_reality.md) | 40+ | 0 | 40+ |
| [esports](domains/esports.md) | 40+ | 0 | 40+ |
| [cannabis](domains/cannabis.md) | 30+ | 0 | 30+ |
| [psychedelics](domains/psychedelics.md) | 30+ | 0 | 30+ |
| [longevity](domains/longevity.md) | 40+ | 0 | 40+ |
| [wellness](domains/wellness.md) | 40+ | 0 | 40+ |
| [philosophy](domains/philosophy.md) | 47 | 0 | 47 |
| [history](domains/history.md) | 61 | 0 | 61 |
| [psychology](domains/psychology.md) | 52 | 0 | 52 |
| [sociology](domains/sociology.md) | 54 | 0 | 54 |
| [anthropology](domains/anthropology.md) | 43 | 0 | 43 |
| [political_science](domains/political_science.md) | 44 | 0 | 44 |
| [linguistics](domains/linguistics.md) | 51 | 0 | 51 |
| [archaeology](domains/archaeology.md) | 47 | 0 | 47 |
| [geography](domains/geography.md) | 50+ | 0 | 50+ |
| [arts](domains/arts.md) | 45 | 0 | 45 |
| [music](domains/music.md) | 49 | 0 | 49 |
| [sports](domains/sports.md) | 57 | 0 | 57 |
| [food](domains/food.md) | 66 | 0 | 66 |
| [fashion](domains/fashion.md) | 66 | 0 | 66 |
| [home](domains/home.md) | 68 | 0 | 68 |
| [pets](domains/pets.md) | 81 | 0 | 81 |
| [health](domains/health.md) | 78 | 0 | 78 |
| [beauty](domains/beauty.md) | 90 | 0 | 90 |
| [automotive](domains/automotive.md) | 40+ | 0 | 40+ |
| [travel](domains/travel.md) | 40+ | 0 | 40+ |
| [countries](domains/countries.md) | 183+ | 0 | 183+ |

**Total: 97 domain files, 13,269 lines**