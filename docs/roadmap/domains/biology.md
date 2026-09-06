# Biology — Roadmap

> **Domain:** Biology | **Status:** Planning | **Last Updated:** 2026-09-06
> **Total Modules:** 95 across 20 sub-disciplines
> **Implemented:** 0 | **Planned:** 95

## Overview

Comprehensive biology domain covering molecular, cellular, organismal, and applied biological sciences. All modules are currently planned — no biology implementations exist in `lib/std/` yet.

## Priority Legend

- 🔴 **Critical** — Foundational modules required by many others
- 🟠 **High** — Core domain modules
- 🟡 **Medium** — Specialized/advanced modules
- 🟢 **Low** — Applied/engineering modules

---

## Quanta Biology Stdlib

| Category | Module | Priority | Status | Version | Dependencies | Quanta Module | Description |
|----------|--------|----------|--------|---------|--------------|---------------|-------------|
| Molecular | DNA | 🔴 Critical | 🔲 planned | — | — | `std/bio/molecular/dna` | DNA structure, replication, repair, recombination |
| Molecular | RNA | 🔴 Critical | 🔲 planned | — | DNA | `std/bio/molecular/rna` | Transcription, RNA types, splicing, regulation |
| Molecular | Protein | 🔴 Critical | 🔲 planned | — | DNA | `std/bio/molecular/protein` | Translation, folding, structure, function |
| Molecular | Gene Expression | 🟠 High | 🔲 planned | — | DNA | `std/bio/molecular/gene_expression` | Regulation, epigenetics, transcriptomics |
| Cell | Organelles | 🔴 Critical | 🔲 planned | — | — | `std/bio/cell/organelles` | Nucleus, mitochondria, ER, Golgi, lysosomes |
| Cell | Division | 🟠 High | 🔲 planned | — | Organelles | `std/bio/cell/division` | Mitosis, meiosis, cell cycle control |
| Cell | Signaling | 🟠 High | 🔲 planned | — | Organelles | `std/bio/cell/signaling` | Receptors, pathways, signal transduction |
| Cell | Death | 🟡 Medium | 🔲 planned | — | Signaling | `std/bio/cell/death` | Apoptosis, necrosis, autophagy |
| Genetics | Mendelian | 🔴 Critical | 🔲 planned | — | DNA | `std/bio/genetics/mendelian` | Inheritance patterns, segregation, linkage |
| Genetics | Molecular | 🟠 High | 🔲 planned | — | DNA | `std/bio/genetics/molecular` | Gene structure, mutation, repair mechanisms |
| Genetics | Population | 🟠 High | 🔲 planned | — | Mendelian | `std/bio/genetics/population` | Hardy-Weinberg, allele frequencies, drift |
| Genetics | Genomics | 🟡 Medium | 🔲 planned | — | Molecular | `std/bio/genetics/genomics` | Genome sequencing, annotation, comparison |
| Developmental | Embryogenesis | 🟠 High | 🔲 planned | — | Cell | `std/bio/dev/embryogenesis` | Fertilization, gastrulation, organogenesis |
| Developmental | Differentiation | 🟠 High | 🔲 planned | — | Embryogenesis | `std/bio/dev/differentiation` | Stem cells, lineage commitment, morphogens |
| Developmental | Regeneration | 🟡 Medium | 🔲 planned | — | Differentiation | `std/bio/dev/regeneration` | Tissue repair, stem cell niches, limb regrowth |
| Developmental | Aging | 🟡 Medium | 🔲 planned | — | Differentiation | `std/bio/dev/aging` | Senescence, telomeres, longevity pathways |
| Evolution | Natural Selection | 🔴 Critical | 🔲 planned | — | Genetics | `std/bio/evo/selection` | Adaptation, fitness, selection mechanisms |
| Evolution | Speciation | 🟠 High | 🔲 planned | — | Selection | `std/bio/evo/speciation` | Isolation, divergence, hybrid zones |
| Evolution | Phylogenetics | 🟠 High | 🔲 planned | — | Selection | `std/bio/evo/phylogenetics` | Trees, cladistics, molecular clocks |
| Ecology | Population | 🔴 Critical | 🔲 planned | — | — | `std/bio/ecology/population` | Growth models, carrying capacity, demography |
| Ecology | Community | 🟠 High | 🔲 planned | — | Population | `std/bio/ecology/community` | Species interactions, succession, diversity |
| Ecology | Ecosystem | 🟠 High | 🔲 planned | — | Community | `std/bio/ecology/ecosystem` | Energy flow, nutrient cycling, biomes |
| Ecology | Global | 🟡 Medium | 🔲 planned | — | Ecosystem | `std/bio/ecology/global` | Biosphere, climate change, conservation |
| Marine | Oceanography | 🟠 High | 🔲 planned | — | — | `std/bio/marine/oceanography` | Currents, zones, marine chemistry |
| Marine | Fisheries | 🟡 Medium | 🔲 planned | — | Oceanography | `std/bio/marine/fisheries` | Stock assessment, aquaculture, management |
| Marine | Coral | 🟡 Medium | 🔲 planned | — | Oceanography | `std/bio/marine/coral` | Reef ecology, bleaching, symbiosis |
| Marine | Deep Sea | 🟡 Medium | 🔲 planned | — | Oceanography | `std/bio/marine/deep` | Abyssal zones, hydrothermal vents, adaptations |
| Microbiology | Bacteriology | 🔴 Critical | 🔲 planned | — | — | `std/bio/micro/bacteria` | Bacterial structure, growth, pathogenesis |
| Microbiology | Virology | 🔴 Critical | 🔲 planned | — | — | `std/bio/micro/virology` | Viral structure, replication, classification |
| Microbiology | Parasitology | 🟠 High | 🔲 planned | — | — | `std/bio/micro/parasitology` | Protozoa, helminths, host-parasite interactions |
| Microbiology | Mycology | 🟠 High | 🔲 planned | — | — | `std/bio/micro/mycology` | Fungal biology, pathogenesis, symbiosis |
| Microbiology | Microbiome | 🟡 Medium | 🔲 planned | — | Bacteriology | `std/bio/micro/microbiome` | Gut flora, dysbiosis, metagenomics |
| Botany | Physiology | 🟠 High | 🔲 planned | — | — | `std/bio/botany/physiology` | Photosynthesis, transport, tropisms |
| Botany | Taxonomy | 🟠 High | 🔲 planned | — | — | `std/bio/botany/taxonomy` | Classification, nomenclature, systematics |
| Botany | Ethnobotany | 🟡 Medium | 🔲 planned | — | — | `std/bio/botany/ethno` | Traditional uses, medicinal plants, agriculture |
| Zoology | Mammalogy | 🟠 High | 🔲 planned | — | — | `std/bio/zoo/mammal` | Mammalian biology, behavior, conservation |
| Zoology | Ornithology | 🟡 Medium | 🔲 planned | — | — | `std/bio/zoo/bird` | Avian biology, migration, ecology |
| Zoology | Herpetology | 🟡 Medium | 🔲 planned | — | — | `std/bio/zoo/reptile` | Reptile and amphibian biology |
| Zoology | Ichthyology | 🟡 Medium | 🔲 planned | — | — | `std/bio/zoo/fish` | Fish biology, aquatic adaptations |
| Zoology | Entomology | 🟠 High | 🔲 planned | — | — | `std/bio/zoo/insect` | Insect biology, metamorphosis, sociality |
| Zoology | Primatology | 🟡 Medium | 🔲 planned | — | Mammalogy | `std/bio/zoo/primate` | Primate evolution, behavior, cognition |
| Neuroscience | Cellular | 🔴 Critical | 🔲 planned | — | — | `std/bio/neuro/cellular` | Neurons, glia, synapses, ion channels |
| Neuroscience | Systems | 🟠 High | 🔲 planned | — | Cellular | `std/bio/neuro/systems` | Sensory, motor, autonomic systems |
| Neuroscience | Cognitive | 🟠 High | 🔲 planned | — | Systems | `std/bio/neuro/cognitive` | Learning, memory, decision-making |
| Neuroscience | Computational | 🟡 Medium | 🔲 planned | — | Systems | `std/bio/neuro/computational` | Neural networks, modeling, brain simulation |
| Neuroscience | Clinical | 🟡 Medium | 🔲 planned | — | Cognitive | `std/bio/neuro/clinical` | Neurological disorders, neuropharmacology |
| Anatomy | Gross | 🔴 Critical | 🔲 planned | — | — | `std/bio/anatomy/gross` | Macroscopic structure, organ systems |
| Anatomy | Microscopic | 🟠 High | 🔲 planned | — | Gross | `std/bio/anatomy/micro` | Histology, tissue types, cellular architecture |
| Anatomy | Developmental | 🟠 High | 🔲 planned | — | Gross | `std/bio/anatomy/dev` | Embryonic development, congenital anomalies |
| Anatomy | Radiological | 🟡 Medium | 🔲 planned | — | Gross | `std/bio/anatomy/radio` | Imaging, MRI, CT, ultrasound anatomy |
| Physiology | Human | 🔴 Critical | 🔲 planned | — | — | `std/bio/physio/human` | Organ systems, homeostasis, integration |
| Physiology | Animal | 🟠 High | 🔲 planned | — | — | `std/bio/physio/animal` | Comparative physiology, adaptations |
| Physiology | Plant | 🟠 High | 🔲 planned | — | — | `std/bio/physio/plant` | Water transport, nutrition, hormone signaling |
| Physiology | Exercise | 🟡 Medium | 🔲 planned | — | Human | `std/bio/physio/exercise` | Metabolism, cardiovascular, performance |
| Pathology | Anatomic | 🟠 High | 🔲 planned | — | Anatomy | `std/bio/path/anatomic` | Tissue changes, autopsy, histopathology |
| Pathology | Clinical | 🟠 High | 🔲 planned | — | Physiology | `std/bio/path/clinical` | Lab medicine, biomarkers, diagnostics |
| Pathology | Molecular | 🟡 Medium | 🔲 planned | — | Genetics | `std/bio/path/molecular` | Molecular diagnostics, precision medicine |
| Pathology | Forensic | 🟡 Medium | 🔲 planned | — | Anatomic | `std/bio/path/forensic` | Cause of death, toxicology, DNA evidence |
| Immunology | Innate | 🔴 Critical | 🔲 planned | — | — | `std/bio/immuno/innate` | Barriers, phagocytes, complement, inflammation |
| Immunology | Adaptive | 🟠 High | 🔲 planned | — | Innate | `std/bio/immuno/adaptive` | T cells, B cells, antibodies, memory |
| Immunology | Autoimmunity | 🟠 High | 🔲 planned | — | Adaptive | `std/bio/immuno/auto` | Self-tolerance, autoimmune diseases |
| Immunology | Transplantation | 🟡 Medium | 🔲 planned | — | Adaptive | `std/bio/immuno/transplant` | Graft rejection, HLA matching, immunosuppression |
| Immunology | Cancer | 🟠 High | 🔲 planned | — | Adaptive | `std/bio/immuno/cancer` | Tumor immunology, immunotherapy, checkpoints |
| Immunology | Vaccinology | 🟠 High | 🔲 planned | — | Adaptive | `std/bio/immuno/vaccine` | Vaccine design, adjuvants, clinical trials |
| Pharmacology | Mechanisms | 🔴 Critical | 🔲 planned | — | Biochemistry | `std/bio/pharm/mechanisms` | Drug-receptor interactions, signaling |
| Pharmacology | Toxicology | 🟠 High | 🔲 planned | — | Mechanisms | `std/bio/pharm/toxicology` | Dose-response, adverse effects, poisoning |
| Pharmacology | Clinical | 🟠 High | 🔲 planned | — | Mechanisms | `std/bio/pharm/clinical` | Clinical trials, therapeutics, dosing |
| Pharmacology | Pharmacokinetics | 🟠 High | 🔲 planned | — | Mechanisms | `std/bio/pharm/pk` | ADME: absorption, distribution, metabolism, excretion |
| Pharmacology | Pharmacodynamics | 🟠 High | 🔲 planned | — | Mechanisms | `std/bio/pharm/pd` | Drug effects, mechanisms, efficacy |
| Biophysics | Structural | 🔴 Critical | 🔲 planned | — | — | `std/biophys/structural` | X-ray, NMR, cryo-EM structure determination |
| Biophysics | Single Molecule | 🟠 High | 🔲 planned | — | Structural | `std/biophys/single_mol` | AFM, optical tweezers, FRET |
| Biophysics | Membrane | 🟠 High | 🔲 planned | — | Structural | `std/biophys/membrane` | Lipid bilayers, ion channels, transport |
| Biophysics | Motor | 🟡 Medium | 🔲 planned | — | Single Molecule | `std/biophys/motor` | Muscle contraction, kinesin, dynein |
| Biophysics | Imaging | 🟠 High | 🔲 planned | — | Structural | `std/biophys/imaging` | Fluorescence, confocal, super-resolution |
| Biophysics | Simulation | 🟡 Medium | 🔲 planned | — | Single Molecule | `std/biophys/simulation` | MD simulations, docking, free energy |
| Bioinformatics | Sequence | 🔴 Critical | 🔲 planned | — | — | `std/bioinfo/sequence` | Alignment, assembly, annotation, BLAST |
| Bioinformatics | Structure | 🟠 High | 🔲 planned | — | Sequence | `std/bioinfo/structure` | Protein structure prediction, AlphaFold |
| Bioinformatics | Systems | 🟠 High | 🔲 planned | — | Sequence | `std/bioinfo/systems` | Pathway analysis, network biology |
| Bioinformatics | Database | 🟠 High | 🔲 planned | — | Sequence | `std/bioinfo/database` | GenBank, UniProt, PDB, KEGG |
| Bioinformatics | Tool | 🟡 Medium | 🔲 planned | — | Sequence | `std/bioinfo/tool` | Biopython, Bioconductor, workflows |
| Bioinformatics | Pipeline | 🟡 Medium | 🔲 planned | — | Tool | `std/bioinfo/pipeline` | NGS pipelines, RNA-seq, variant calling |
| Bioinformatics | Visualization | 🟡 Medium | 🔲 planned | — | Tool | `std/bioinfo/viz` | Genome browsers, Circos, heatmaps |
| Biotechnology | Genetic Engineering | 🔴 Critical | 🔲 planned | — | Molecular | `std/biotech/genetic` | CRISPR, cloning, vectors, transformation |
| Biotechnology | Cell Therapy | 🟠 High | 🔲 planned | — | Cell | `std/biotech/cell` | CAR-T, stem cell therapy, immunotherapy |
| Biotechnology | Gene Therapy | 🟠 High | 🔲 planned | — | Molecular | `std/biotech/gene` | Viral vectors, gene delivery, clinical trials |
| Biotechnology | Synthetic Biology | 🟠 High | 🔲 planned | — | Genetic Engineering | `std/biotech/synthetic` | Genetic circuits, metabolic engineering |
| Biotechnology | Fermentation | 🟡 Medium | 🔲 planned | — | Microbiology | `std/biotech/fermentation` | Bioprocessing, scale-up, bioreactors |
| Biotechnology | Biosensor | 🟡 Medium | 🔲 planned | — | Biophysics | `std/biotech/biosensor` | Diagnostic devices, wearable sensors |
| Biomedical Eng | Imaging | 🟠 High | 🔲 planned | — | — | `std/biomed/eng/imaging` | MRI, CT, PET, ultrasound engineering |
| Biomedical Eng | Prosthetics | 🟠 High | 🔲 planned | — | — | `std/biomed/eng/prosthetics` | Limb prosthetics, neural interfaces |
| Biomedical Eng | Biomaterials | 🟠 High | 🔲 planned | — | — | `std/biomed/eng/materials` | Biocompatibility, scaffolds, implants |
| Biomedical Eng | Tissue Engineering | 🟡 Medium | 🔲 planned | — | Biomaterials | `std/biomed/eng/tissue` | Organ printing, regenerative medicine |
| Biomedical Eng | Neural Engineering | 🟡 Medium | 🔲 planned | — | Neuroscience | `std/biomed/eng/neural` | Brain-computer interfaces, deep brain stimulation |
| Biomedical Eng | Rehabilitation | 🟡 Medium | 🔲 planned | — | Prosthetics | `std/biomed/eng/rehab` | Assistive technology, physical therapy devices |

---

## Summary Statistics

| Sub-Discipline | Modules | Critical | High | Medium | Planned |
|----------------|---------|----------|------|--------|---------|
| Molecular Biology | 4 | 3 | 1 | 0 | 4 |
| Cell Biology | 4 | 1 | 2 | 1 | 4 |
| Genetics | 4 | 1 | 2 | 1 | 4 |
| Developmental Biology | 4 | 0 | 2 | 2 | 4 |
| Evolution | 3 | 1 | 2 | 0 | 3 |
| Ecology | 4 | 1 | 2 | 1 | 4 |
| Marine Biology | 4 | 0 | 1 | 3 | 4 |
| Microbiology | 5 | 2 | 2 | 1 | 5 |
| Botany | 3 | 0 | 2 | 1 | 3 |
| Zoology | 6 | 0 | 2 | 4 | 6 |
| Neuroscience | 5 | 1 | 2 | 2 | 5 |
| Anatomy | 4 | 1 | 2 | 1 | 4 |
| Physiology | 4 | 1 | 2 | 1 | 4 |
| Pathology | 4 | 0 | 2 | 2 | 4 |
| Immunology | 6 | 1 | 4 | 1 | 6 |
| Pharmacology | 5 | 1 | 4 | 0 | 5 |
| Biophysics | 6 | 1 | 3 | 2 | 6 |
| Bioinformatics | 7 | 1 | 3 | 3 | 7 |
| Biotechnology | 6 | 1 | 3 | 2 | 6 |
| Biomedical Engineering | 6 | 0 | 3 | 3 | 6 |
| **Total** | **95** | **17** | **46** | **32** | **95** |

---

## Implementation Phases

### Phase 1: Foundations (Critical Priority)
- DNA, Organelles, Mendelian, Natural Selection, Population (Ecology)
- Bacteriology, Virology, Cellular (Neuroscience), Gross, Human
- Innate, Mechanisms, Structural, Sequence, Genetic Engineering, Imaging (Biomed)

### Phase 2: Core Systems (High Priority)
- RNA, Protein, Division, Signaling, Molecular (Genetics), Population (Genetics)
- Embryogenesis, Differentiation, Speciation, Phylogenetics, Community, Ecosystem
- Oceanography, Parasitology, Mycology, Physiology (Botany), Taxonomy
- Mammalogy, Entomology, Systems (Neuroscience), Cognitive, Microscopic, Developmental
- Animal, Plant, Adaptive, Autoimmunity, Cancer, Vaccinology
- Toxicology, Clinical (Pharm), PK, PD, Single Molecule, Membrane, Imaging (Biophysics)
- Structure (Bioinformatics), Systems (Bioinformatics), Database, Cell Therapy, Gene Therapy
- Synthetic Biology, Prosthetics, Biomaterials

### Phase 3: Advanced/Applied (Medium Priority)
- Gene Expression, Death, Genomics, Regeneration, Aging, Global
- Fisheries, Coral, Deep Sea, Microbiome, Ethnobotany
- Ornithology, Herpetology, Ichthyology, Primatology, Computational, Clinical (Neuroscience)
- Radiological, Exercise, Anatomic, Clinical (Path), Molecular (Path), Forensic
- Transplantation, Motor, Simulation, Tool, Pipeline, Visualization
- Fermentation, Biosensor, Tissue Engineering, Neural Engineering, Rehabilitation

---

## Notes

- All modules currently have **no implementation** in `lib/std/`
- Biology domain is greenfield — no existing Quanta code to build upon
- Cross-domain dependencies (Biochemistry, Chemistry, Physics) noted where applicable
- Priority based on foundational importance and dependency graph
