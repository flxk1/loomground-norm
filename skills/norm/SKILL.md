---
name: norm
description: 'Lift a sentence of running text into a RuleFacet (subject, modal, modal_phrase, action, condition, exception, consequence, incident, counterparty, language, confidence) and on into a rendered deontic formula O/P/F(bearer : action) with unless/if scopes, in the 24 EU languages. Use when the user wants a norm extracted from prose, asks which modal phrases loomground-norm recognises in a language (shall, must not, darf keine, doit, non può), or needs the obligation/prohibition/permission/right class of a sentence; triggers on "extract the rule", "lift this to deontic", "which modal is this", "RuleFacet". Ranking of sources, jurisdiction and conflict resolution belong to the other planes.'
allowed-tools: norm_extract
metadata:
  version: "1.0"
---

# loomground-norm — the lift, reference card

Primary path: call `norm_extract` with `{"text": "The operator shall delete personal data unless a legal hold applies.", "language": "en"}`; the `result` carries the RuleFacets and, per facet, the lifted deontic formula rendered (`O(the operator : delete personal data) unless [a legal hold applies]`).

Shell fallback: `python3 -c 'from loomground_norm import extract_rules, formula_from_rule; r = extract_rules("The operator shall delete personal data unless a legal hold applies.")[0]; print(r); print(formula_from_rule(r).render())'` (package `loomground-norm`).

loomground-norm is the lift from running text into the deontic language; the grammar is loomground-deontic's. Values here come from `src/loomground_norm/rule_extractor.py` (the per-language registry) and `deontic.MODAL_TO_OP`.

## Lift

`extract_rules(text) → [RuleFacet]` · `formula_from_rule(rule) → DeonticFormula` (via `deontic.formula_from_fields`) · `extract_formulae(text)` does both.

## RuleFacet fields

| field | content |
|---|---|
| `subject` | the regulated subject, lowercase canonical form |
| `modal` | `obligation` · `prohibition` · `permission` · `right` |
| `modal_phrase` | the matched surface phrase (`must`, `darf keine`, `doit`) |
| `action` | the verb phrase the rule binds the subject to |
| `condition` | applicability condition, verbatim (`where`, `if`, `sofern`, `si` …) |
| `exception` | scoping carve-out, verbatim (`unless`, `except`, `unbeschadet`, `sans préjudice de` …) |
| `consequence` | the `otherwise …` / `failing which …` branch |
| `incident` | Hohfeld position of the addressee: `duty` · `privilege` · `power` · `immunity` · `disability`; set by `attach_incidents` |
| `counterparty` | the correlative role, when named |
| `condition_kind` | `suspensive` · `resolutive` · unclassified |
| `addressee_resolved` | `False` for an agentless passive (the subject is the patient) |
| `language` | ISO 639-1, one of the 24 EU languages; `en` fallback |
| `confidence` | 1.0 = all five slots populated |
| `raw_sentence` | the source sentence |

## Operator map (`deontic.MODAL_TO_OP`)

obligation → `O` · permission → `P` · prohibition → `F` · right → `P`. A surface right lifts to `P`; the claim-right is carried by `incident`.

## Executed lift

Each row is `extract_rules(s)[0]` and `formula_from_rule(rule).render()`, run against 0.1.0.

| sentence | subject | modal | phrase | action | condition | exception | lang | conf. | formula |
|---|---|---|---|---|---|---|---|---|---|
| The operator must delete personal data within 30 days after the contract ends. | `the operator` | `obligation` | `must` | `delete personal data within 30 days after the contract ends` | — | — | en | 0.7 | `O(the operator : delete personal data within 30 days after the contract ends)` |
| The operator shall not transfer personal data outside the EU. | `the operator` | `prohibition` | `shall not` | `transfer personal data outside the EU` | — | — | en | 0.7 | `F(the operator : transfer personal data outside the EU)` |
| The operator may retain invoices for ten years. | `the operator` | `permission` | `may` | `retain invoices for ten years` | — | — | en | 0.7 | `P(the operator : retain invoices for ten years)` |
| The operator shall delete personal data unless a legal hold applies. | `the operator` | `obligation` | `shall` | `delete personal data` | — | `a legal hold applies` | en | 0.8 | `O(the operator : delete personal data) unless [a legal hold applies]` |
| The data subject has the right to obtain a copy of the data. | `the data subject` | `right` | `has the right` | `to obtain a copy of the data` | — | — | en | 0.7 | `P(the data subject : to obtain a copy of the data)` |
| Der Anbieter darf keine personenbezogenen Daten weitergeben. | `der anbieter` | `prohibition` | `darf keine` | `personenbezogenen Daten weitergeben` | — | — | de | 0.7 | `F(der anbieter : personenbezogenen Daten weitergeben)` |
| Le responsable du traitement doit effacer les données à caractère personnel. | `le responsable du traitement` | `obligation` | `doit` | `effacer les données à caractère personnel` | — | — | fr | 0.7 | `O(le responsable du traitement : effacer les données à caractère personnel)` |
| Il fornitore non può trasferire i dati personali. | `il fornitore` | `prohibition` | `non può` | `trasferire i dati personali` | — | — | it | 0.7 | `F(il fornitore : trasferire i dati personali)` |

## Modal phrases, 24 languages

Surface phrase → modal class, from the registry (`_MODAL_CLASS_EN`, `_MODAL_CLASS_DE`, `_GENERIC_SPECS`). Longest phrase wins. Language is detected per sentence; `en` is the fallback.

| code | language | obligation | prohibition | permission | right |
|---|---|---|---|---|---|
| en | English | `shall` · `must` · `is required` · `are required` | `shall not` · `must not` · `may not` · `is prohibited` · `are prohibited` · `shall be prohibited` · `shall be banned` · `is banned` · `are banned` · `be prohibited` | `may` | `has the right` · `have the right` · `shall have the right` · `is entitled` · `are entitled` · `is empowered` · `are empowered` |
| de | German | `muss` · `müssen` · `ist verpflichtet` · `sind verpflichtet` · `hat` · `haben` | `dürfen nicht` · `darf nicht` · `dürfen keine` · `darf keine` | `darf` · `dürfen` | `ist berechtigt` · `hat das recht` |
| fr | French | `doit` · `doivent` · `est tenu de` · `sont tenus de` · `est tenu d'` | `ne doit pas` · `ne peut pas` · `ne peuvent pas` · `il est interdit de` | `peut` · `peuvent` | `a le droit` · `ont le droit` |
| it | Italian | `deve` · `devono` · `è tenuto a` · `sono tenuti a` · `è obbligato a` | `non deve` · `non può` · `non possono` · `è vietato` | `può` · `possono` | `ha diritto` · `hanno diritto` |
| es | Spanish | `debe` · `deben` · `deberá` · `deberán` · `está obligado a` | `no debe` · `no podrá` · `no podrán` · `está prohibido` | `puede` · `pueden` · `podrá` | `tiene derecho` · `tienen derecho` |
| nl | Dutch | `moet` · `moeten` · `is verplicht` · `zijn verplicht` · `dient` · `dienen` | `mag niet` · `mogen niet` · `is verboden` | `mag` · `mogen` · `kan` · `kunnen` | `heeft het recht` · `hebben het recht` |
| pt | Portuguese | `deve` · `devem` · `está obrigado a` · `fica obrigado a` | `não pode` · `não deve` · `é proibido` | `pode` · `podem` | `tem direito` · `têm direito` |
| sv | Swedish | `ska` · `skall` · `är skyldig att` | `får inte` · `ska inte` | `får` · `kan` | `har rätt` · `har rätt att` |
| da | Danish | `skal` · `er forpligtet til` | `må ikke` · `kan ikke` | `kan` · `må` | `har ret til` |
| pl | Polish | `musi` · `jest zobowiązany` · `ma obowiązek` · `są zobowiązani` | `nie może` · `zakazuje się` · `nie wolno` | `może` · `mogą` | `ma prawo` · `mają prawo` |
| cs | Czech | `musí` · `je povinen` · `jsou povinni` | `nesmí` · `je zakázáno` | `může` · `mohou` · `smí` | `má právo` · `mají právo` |
| sk | Slovak | `musí` · `je povinný` · `sú povinní` | `nesmie` · `je zakázané` | `môže` · `môžu` · `smie` | `má právo` · `majú právo` |
| ro | Romanian | `trebuie` · `este obligat să` · `are obligația` | `nu trebuie` · `este interzis` · `nu poate` | `poate` · `pot` | `are dreptul` · `au dreptul` |
| sl | Slovenian | `mora` · `morajo` · `je dolžan` | `ne sme` · `prepovedano je` | `lahko` · `sme` | `ima pravico` · `imajo pravico` |
| hr | Croatian | `mora` · `moraju` · `dužan je` | `ne smije` · `zabranjeno je` | `može` · `mogu` · `smije` | `ima pravo` · `imaju pravo` |
| el | Greek | `πρέπει` · `υποχρεούται` · `οφείλει` | `δεν επιτρέπεται` · `απαγορεύεται` · `δεν πρέπει` | `μπορεί` · `δύναται` | `έχει δικαίωμα` · `έχουν δικαίωμα` |
| bg | Bulgarian | `трябва` · `длъжен е` · `е длъжен` | `не може` · `забранява се` · `не трябва` | `може` · `могат` | `има право` · `имат право` |
| fi | Finnish | `on velvollinen` · `täytyy` · `on velvoitettu` | `ei saa` · `on kielletty` | `voi` · `saa` | `on oikeus` |
| hu | Hungarian | `köteles` · `kell` | `tilos` · `nem szabad` · `nem lehet` | `lehet` | `jogosult` · `joga van` |
| et | Estonian | `peab` · `on kohustatud` | `ei tohi` · `on keelatud` | `võib` | `on õigus` |
| lt | Lithuanian | `privalo` · `turi` | `negali` · `draudžiama` | `gali` | `turi teisę` |
| lv | Latvian | `ir pienākums` · `nodrošina` | `nedrīkst` · `ir aizliegts` | `var` · `drīkst` | `ir tiesības` |
| ga | Irish | `ní mór` · `déanfaidh` | `ní cheadaítear` · `toirmiscfear` | `féadfaidh` · `féadann` | `tá ceart` · `tá sé de cheart` |
| mt | Maltese | `għandu` · `huwa obbligat` | `ma jistax` · `huwa pprojbit` | `jista'` · `jistgħu` | `għandu dritt` |

## Not expressible

Which source outranks which (loomground-topos), jurisdiction and lifecycle (loomground-legal), who wins a conflict (loomground-solver).

Same card, README-linked copy: `../../docs/language-card.md`.
