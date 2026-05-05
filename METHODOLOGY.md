# Note méthodologique — ThreatHeatMap

> Document de méthodologie analytique. Lecture recommandée avant toute
> exploitation des heat maps produites par l'outil dans un livrable client.

| Champ              | Valeur                                                         |
|--------------------|----------------------------------------------------------------|
| Version document   | 1.1.0                                                          |
| Phase projet       | Phase 1 (squelette + données synthétiques)                     |
| Périmètre          | Production de heat maps sectorielles d'acteurs malveillants    |
| Public visé        | Analystes CTI, RSSI clients, équipes Threat Intelligence       |
| Niveau de confiance| Outil de support à l'analyse, **non** scoring décisionnel auto |

---

## 1. Objectif analytique

ThreatHeatMap est un outil interne d'aide à la rédaction des rapports CTI
mensuels destinés à des clients sectoriels (télécoms, opérateurs de câbles
sous-marins, transport maritime, énergie, etc.). Il produit, pour un secteur
client donné et une fenêtre temporelle paramétrable, une visualisation
positionnant les acteurs malveillants sur un plan à deux dimensions :

- **Axe Y — Intent** : probabilité que l'acteur cible *spécifiquement* le
  secteur du client.
- **Axe X — Opportunity** : facilité d'exploitation pour cet acteur, étant
  donné le profil d'exposition externe du client.

Le quadrant supérieur droit (haute intent × haute opportunity) concentre
les acteurs qu'il est analytiquement justifié de prioriser dans un livrable
client. Les autres quadrants servent à contextualiser, pas à éliminer.

L'outil **n'a pas vocation à se substituer au jugement de l'analyste**. Les
scores produits sont des *aides à la priorisation*, à corroborer avec les
indicateurs métiers (revendications publiques, IoC observés sur le périmètre,
analyse contextuelle de la cinétique).

---

## 2. Variables

### 2.1. `P_sect` — probabilité de ciblage sectoriel

Probabilité conditionnelle que l'acteur cible le secteur sélectionné, sur
la fenêtre temporelle choisie.

- **Plage** : [0, 1].
- **Calcul dynamique (par défaut)** :
  ```
  P_sect = victimes_dans_le_secteur(actor, sector, fenetre)
         / victimes_totales(actor, fenetre)
  ```
  Le calcul s'appuie sur les victimes documentées dans la fenêtre. Un acteur
  qui frappe massivement la santé et accessoirement le télécom verra son
  `P_sect_télécom` rester modéré quel que soit le total absolu de victimes.
- **Repli baseline** : si l'acteur n'a **aucune** victime documentée dans la
  fenêtre (toutes industries confondues), le runtime utilise la valeur
  baseline `sector_targeting[<sector>].p_sect` du référentiel acteur. Ce
  repli évite l'effet d'écrasement d'acteurs à cadence basse mais à intent
  sectoriel élevé (typiquement les APT étatiques entre deux opérations
  publiques). La provenance est exposée dans le champ `p_sect_source`
  (`victims_ratio` | `baseline_fallback`) afin que l'analyste sache si la
  position d'un acteur repose sur des données observées ou sur une
  hypothèse de baseline.
- **Fenêtre de référence** : 3, 6 ou 12 mois glissants. Le choix de la
  fenêtre conditionne fortement `P_sect`. Une heat map sur 3 mois produit
  une lecture *opérationnelle* (qui frappe maintenant), une heat map sur
  12 mois produit une lecture *stratégique* (qui s'intéresse durablement
  au secteur).

### 2.2. `P_ttp` — couverture / spécificité TTP

Coefficient de couverture des techniques (ATT&CK) de l'acteur sur le
secteur considéré.

- **Plage** : [0, 1].
- **Phase 1** : valeur figée par couple `(actor, sector)` dans
  `sector_targeting[<sector>].p_ttp` du référentiel.
- **Phase 2 (à venir)** : recalcul à partir des techniques attribuées à
  l'acteur dans le STIX/TAXII MITRE ATT&CK et de la matrice de pertinence
  technique × secteur. La structure `sector_targeting` est conçue pour
  accueillir cette évolution sans modifier les appelants.

### 2.3. `SecurityScore` — score d'exposition externe

Score d'exposition externe agrégé pour le couple `(actor, client)`.

- **Plage** : [0, 100]. Plus élevé = exposition perçue plus forte = facilité
  d'exploitation plus grande pour l'acteur.
- **Sources de la valeur runtime, par ordre de priorité** :
  1. Override saisi dans l'UI (champ "SecurityScore Override").
  2. Override par profil client : `security_score_overrides_by_client[client_id]`.
  3. Défaut acteur : `default_security_score`.
  4. Défaut global : `config.DEFAULT_SECURITY_SCORE`.
  La provenance retenue est exposée dans `security_score_source`.
- **Limite Phase 1** : valeur saisie manuellement, donc **biais analyste
  direct**. À remplacer en Phase 2-3 par un agrégat issu de scanners ASM
  (Attack Surface Management), de sondes externes ou d'audits récents.
- **Sélecteur "Client profile"** : l'UI permet de basculer entre profils
  clients pré-paramétrés. Chaque profil porte son jeu d'overrides ; à
  terme il portera également le mapping des secteurs critiques pour ce
  client.

---

## 3. Formules

Les formules sont enregistrées dans `scoring/formulas.py` sous forme d'un
dictionnaire `FORMULAS`. La formule active est sélectionnée par
`config.ACTIVE_FORMULA`. Ajouter une formule revient à ajouter une entrée
au dictionnaire ; aucun appelant n'a à être modifié.

### 3.1. `geometric_mean_v1` (formule de référence initiale)

```
Y = sqrt(P_sect × P_ttp) × 100
X = SecurityScore × P_ttp
```

Moyenne géométrique pure. Avantage : pénalise fortement les acteurs pour
lesquels une des deux probabilités est faible, ce qui est cohérent avec un
modèle conjonctif (« il faut à la fois l'intent **et** la couverture TTP »).

Inconvénient : effondre l'acteur à `Y = 0` dès qu'une des deux probabilités
est nulle, y compris en cas de simple absence de signal sur la fenêtre.
Visuellement, cela peut suggérer à tort qu'un acteur n'est plus pertinent.

### 3.2. `geometric_mean_floored_v1` (formule active par défaut)

```
Y = sqrt( max(P_sect, ε) × max(P_ttp, ε) ) × 100      avec ε = 0.05
X = SecurityScore × P_ttp
```

Variante avec plancher `ε = 0.05` appliqué indépendamment sur chaque
probabilité avant la moyenne géométrique. Conserve le caractère conjonctif
de la formule v1 mais évite l'effondrement à zéro.

- **Conséquence** : `Y_min ≈ 5.0` quand `P_sect = P_ttp = 0`. Cette valeur
  est ancrée par un test unitaire (`test_floored_formula_floor_contract_at_zero_zero`).
- **Quand l'utiliser** : par défaut. La formule active est documentée dans
  le pied de page de l'UI à chaque rendu.
- **Quand préférer la v1** : analyses comparatives où l'on veut isoler les
  acteurs strictement absents du signal, ou audit de données.

### 3.3. Évolutions envisagées

- Pondération exponentielle décroissante des victimes en fonction de leur
  ancienneté.
- Bonus / malus sur `P_sect` en fonction de la criticité métier du secteur
  pour le client (mapping à venir dans le profil client).
- Formule à pondérations explicites `α × P_sect + β × P_ttp` pour les
  cas où l'analyste souhaite un comportement additif et non conjonctif.

---

## 4. Sources de données

### 4.1. Phase 1 — fixture synthétique uniquement

Toutes les données affichées en Phase 1 proviennent du fichier
`data/fixtures/actors_demo.json`. Les noms d'acteurs sont **réels**, les
TTPs MITRE ATT&CK sont **réels** (technique IDs valides), mais les
**victimes sont simulées**, les `P_sect` baseline et `P_ttp` sont
**hand-picked**, et les `SecurityScore` sont des **valeurs placeholder**.

La logique de plausibilité par acteur est documentée dans
`data/fixtures/RATIONALE.md` (justifications de la distribution sectorielle,
exclusions argumentées, choix de cadence).

### 4.2. Phase 2 — connecteur MITRE ATT&CK STIX/TAXII (à venir)

- Endpoint : `https://attack-taxii.mitre.org/api/v21/`.
- Collections d'intérêt : Enterprise ATT&CK.
- Données récupérées : Intrusion Sets, techniques associées (relations
  `uses`), secteurs ciblés (champs `x_mitre_industries` lorsqu'ils existent).
- Cache local : 24 heures (configurable via `config.MITRE_CACHE_TTL_HOURS`).
- Licence : Apache 2.0, attribution MITRE requise dans les exports.

### 4.3. Phase 3 — connecteur LocalDLSAdapter (à venir)

Lecture de fichiers JSON/CSV produits par le scraping interne des Data
Leak Sites (DLS) ransomware. La normalisation des secteurs s'appuie sur
`data/sectors.json` (référentiel NIS2 + alias ENISA / `x_mitre_industries`).
L'interface `VictimsAdapter` est commune à toutes les sources.

### 4.4. Phase 4 conditionnelle — `RansomwareLiveAdapter`

Connecteur sur l'API publique `ransomware.live`. Sa licence (CGU section
2.1) restreint l'usage à un cadre **non commercial**. Le projet implémente
les garde-fous suivants :

- Drapeau `config.RANSOMWARE_LIVE_USAGE` ∈ `{"evaluation", "authorized_commercial", "disabled"}`.
- Bannière de licence affichée au démarrage si la source est active.
- Levée d'exception explicite si `disabled` et appel effectué.
- Clause d'attribution `Source: Ransomware.live (https://www.ransomware.live)`
  injectée dans les exports JSON quand cette source est active.

L'usage commercial (livrable client facturé s'appuyant sur ces données)
nécessite une autorisation écrite de l'éditeur. Cf. `README.md` —
section *Data sources & licensing*.

---

## 5. Référentiel sectoriel

Le référentiel canonique est dérivé de la **directive NIS2 ((UE) 2022/2555)**,
Annexes I (entités essentielles) et II (entités importantes). Il est porté
par `data/sectors.json` et expose, pour chaque secteur :

- Le **nom canonique** utilisé dans toute la chaîne (URL, fixture, API,
  exports).
- Le **rattachement NIS2** (annexe I ou II, catégorie réglementaire).
- Une liste d'**alias** (formulations ENISA, valeurs `x_mitre_industries`
  observées dans les Intrusion Sets, terminologies sectorielles
  vernaculaires).

La normalisation `data/sectors.json` est non destructive : un secteur
inconnu côté API renvoie 400 et n'est jamais silencieusement remappé sur
un voisin sémantique. Les alias documentés sont en revanche résolus
automatiquement.

Choix du cadre NIS2 plutôt que NACE / NAICS : meilleure granularité sur
les sous-secteurs critiques (opérateurs de câbles sous-marins, ICT
managed services, infrastructure de marchés financiers) qui sont précisément
ceux pour lesquels la heat map est produite.

---

## 6. Biais connus

| Biais                                            | Origine                                                                               | Mitigation                                                                                          |
|--------------------------------------------------|---------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| Biais analyste sur `SecurityScore`               | Saisie manuelle des valeurs par client                                                | Documenter la source dans le rapport ; viser un remplacement par ASM / sondes externes en Phase 2-3 |
| Biais d'observabilité ransomware                 | Les DLS ne couvrent que les victimes refusant la rançon ; sous-estimation systématique | Croiser avec MITRE et signaux internes ; ne pas exporter `P_sect` brut sans cette mention           |
| Sur-représentation russe                         | Échantillon Phase 1 majoritairement aligné Russie                                     | Volonté assumée pour la cinétique télécoms / câbles ; à élargir lors du branchement MITRE           |
| Cadence vs intent                                | Un acteur silencieux 3 mois peut rester intent élevé                                  | Repli baseline sur `P_sect` + champ `p_sect_source` exposé à l'utilisateur                          |
| Granularité sectorielle inégale                  | NIS2 fusionne certains sous-secteurs (Manufacturing en particulier)                   | Ajouter des secteurs ad hoc dans `sectors.json` au cas par cas ; documenter les ajouts              |
| Plancher ε artificialise les acteurs muets       | `geometric_mean_floored_v1` plante un seuil minimum                                   | Visuel : valeur Y plancher = 5.0 ; documenter la formule active en pied de page UI                  |
| Attribution publique faiblement contestable      | Noms d'acteurs et alias issus de la littérature CTI vendor                            | Conserver les alias dans la fixture ; ne pas verrouiller l'analyste sur un seul vendor naming       |
| Fixture statique vs réalité mouvante             | Phase 1 ne reflète pas l'actualité                                                    | Régénération attendue à chaque cycle de reporting ; passage en Phase 2 dès que possible             |

---

## 7. Limites

- **Mono-utilisateur** : aucune authentification ; outil exécuté localement
  sur le poste de l'analyste.
- **Pas de persistance des paramètres** : à chaque rechargement, l'UI
  repart sur les valeurs par défaut (sector, fenêtre, client). Les exports
  JSON capturent en revanche tous les paramètres effectifs au moment de
  l'export.
- **Pas de versioning des heat maps** : un même rendu produit à deux
  moments différents peut donner des résultats différents (régénération
  de la fixture, mise à jour MITRE, glissement de la fenêtre temporelle).
  Les exports incluent `extracted_at` (UTC) pour traçabilité, mais c'est
  à l'analyste d'archiver les exports avant rédaction.
- **Pas de calcul d'incertitude** : les scores sont produits comme valeurs
  ponctuelles, sans intervalle de confiance. Toute interprétation doit
  rester qualitative.
- **Périmètre français/européen** : le référentiel sectoriel s'aligne sur
  NIS2. Les clients hors UE (États-Unis, Asie) peuvent nécessiter un
  remapping manuel (NAICS, classification client interne).
- **Capture du contexte géopolitique** : non modélisée. Un changement de
  régime d'attribution (ex. Operation Cronos pour LockBit) impose une mise
  à jour manuelle de la fixture / des données MITRE.

---

## 8. Références

### Référentiels normatifs
- Directive (UE) 2022/2555 (« NIS2 »), Annexes I et II.
- ENISA, *Threat Landscape* (publications annuelles).
- NIST SP 800-30, *Guide for Conducting Risk Assessments*.

### Cadres techniques
- MITRE ATT&CK Enterprise (matrice techniques × tactiques).
- STIX 2.1 / TAXII 2.1 (transport et structure des objets ATT&CK).

### Sources opérationnelles
- MITRE ATT&CK STIX/TAXII : `https://attack-taxii.mitre.org/api/v21/`.
- ransomware.live (sous CGU non-commerciales) : `https://www.ransomware.live`.

### Documents internes du projet
- `README.md` — installation, exécution, sources et licences.
- `data/fixtures/RATIONALE.md` — plausibilité par acteur (Phase 1).
- `data/sectors.json` — référentiel sectoriel canonique avec alias.
- `data/schema/actor_schema.json` — schéma de validation d'un objet acteur.
- `scoring/formulas.py` — registre des formules de scoring.
- `scoring/scorer.py` — implémentation `compute_score()` (source de vérité unique).

---

## 9. Historique des révisions

| Version | Date       | Changements principaux                                                                          |
|---------|------------|-------------------------------------------------------------------------------------------------|
| 1.1.0   | 2026-05-04 | Patch v1.1 : formule `geometric_mean_floored_v1` (plancher ε=0.05) active ; fixture régénérée ; schéma JSON acteur ; repli baseline sur `P_sect` documenté ; provenance `p_sect_source` / `security_score_source` exposée. |
| 1.0.0   | 2026-05-04 | Phase 1 initiale : squelette Flask + fixture 10 acteurs ; formule `geometric_mean_v1` ; référentiel NIS2.                                                                              |
