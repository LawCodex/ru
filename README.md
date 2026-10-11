# Russia — federal legislation as Markdown (LawCodex)

Current consolidated texts (актуальные редакции) of the primary federal legislation of the
**Russian Federation** (Российская Федерация), in Russian, as plain Markdown — part of
[LawCodex](https://github.com/LawCodex).

Retrieved: **2026-10-12** (each file carries its own `retrieved` and `last_amended` dates).

## Contents

<!-- COUNTS -->

| Directory | What | Files |
|---|---|---|
| `konstitutsiya/` | Конституция Российской Федерации (with the 2020 amendments and the 2022 changes to Art. 65) | 1 |
| `konstitutsiya/popravki/` | Законы РФ о поправке к Конституции (2008, 2014, 2020) | 5 |
| `kodeksy/` | Codes in force (Кодексы РФ: ГК ч.1–4, НК ч.1–2, УК, УПК, ГПК, АПК, КАС, КоАП, ТК, СК, ЖК, ЗК, БК, ГрК, ВК, ЛК, ВозК, КТМ, КВВТ, УИК…) | 25 |
| `fkz/<year>/` | Федеральные конституционные законы in force or not yet in force | 171 |
| `fz/<year>/` | Федеральные законы in force or not yet in force | … |
| `zakony-rf/` | Законы Российской Федерации (1991–1993), Законы РСФСР and Основы законодательства still in force | … |

<!-- /COUNTS -->

"In force" follows the state (`Состояние`) given by the official database: *Действует с
изменениями*, *Действует без изменений* (in force), *Не вступил в силу* (adopted, not yet in
force). Acts marked *Утратил силу* / *Отменен* / *Не действует* are not included.
Note that most federal laws formally "in force without changes" are amending laws
(«О внесении изменений в …»); they are included because the official source lists them as in
force, but their substance is already merged into the consolidated acts they amend.

### Not covered

- Repealed acts and historical редакции (only the currently applicable редакция is published;
  for acts not yet in force, the first редакция that will enter into force).
- Subordinate legislation: указы and распоряжения of the President, постановления of the
  Government, ministerial orders, regional legislation, court decisions (incl. Constitutional
  Court), international treaties.
- Embedded images (formulas, forms, maps) are not copied; they are linked to the official image
  URL on `actual.pravo.gov.ru`.

## Source

**Официальный интернет-портал правовой информации** (pravo.gov.ru), operated by the Federal
Protective Service (ФСО России) — the official publication source of Russian federal law —
section *«Тексты правовых актов с внесенными изменениями»* at
<http://actual.pravo.gov.ru/>. The texts are retrieved through the JSON API that the site's own
web application uses (`http://actual.pravo.gov.ru:8000/api/ebpi/`: `attrsearch`, `redactions`,
`redtext`). Each file's `source` is the official viewer URL of the act
(`http://actual.pravo.gov.ru/content/content.html#hash=<dochash>`), and its `redaction`
field is the official caption of the редакция used.

The main portal `pravo.gov.ru` and its ИПС «Законодательство России» were not reachable from
the network used to build this repository (timeouts); `actual.pravo.gov.ru` is part of the same
official portal. ConsultantPlus / Garant (commercial) were **not** used.

Editorial notes of the official consolidation (e.g. «(В редакции Федерального закона от … № …)»,
«(Утратил силу - …)», notes on application) are part of the official consolidated text and are
kept verbatim.

## Copyright / licence

Official documents — laws and other normative acts, court decisions and their official
translations — are **not objects of copyright** under Article 1259(6)(1) of the Civil Code of the
Russian Federation (ГК РФ, ст. 1259, п. 6, пп. 1). The portal's robots.txt does not restrict
access to these pages and no terms of use restricting reuse were found. The conversion code in
`scripts/` is released into the public domain (CC0).

The Markdown texts are provided for information; for legally binding texts consult the
official publication (publication.pravo.gov.ru, «Собрание законодательства РФ», «Российская
газета»).

## File format

One Markdown file per act, UTF-8, LF, with YAML front matter:

```yaml
title: О персональных данных
identifier: 152-ФЗ          # official number
type: federal_law           # constitution | constitutional_amendment | code | federal_constitutional_law | federal_law | law
kind: Федеральный закон от 27.07.2006 № 152-ФЗ
jurisdiction: ru
language: ru
date: 2006-07-27            # date of signature
last_amended: 2025-09-01    # date the current редакция applies from
redaction: 45. с 01.09.2025 (№ … от …), актуальная
status: in_force            # in_force | not_yet_in_force
state: Действует с изменениями
publications: [...]         # official publication sources
source: http://actual.pravo.gov.ru/content/content.html#hash=…
retrieved: 2026-10-12
```

Structure (Часть / Раздел / Подраздел / Глава / § / Статья) is mapped to Markdown headings
(`##` … `######`); article numbers with superscripts are kept as `<sup>`. Tables with merged
cells are kept as simple HTML tables; pseudo-graphic (monospaced) blocks as code blocks.

File names are transliterated (Russian passport-style romanisation) and identifier-based:
`fz/2006/fz-2006-152-o-personalnykh-dannykh.md` = Federal Law of 2006 No. 152-ФЗ;
`fkz/1994/fkz-1994-1-o-konstitutsionnom-sude-rossiiskoi-federatsii.md`;
`zakony-rf/zakon-rf-1992-2300-1-o-zashchite-prav-potrebitelei.md` (Roman numeral `-I` → `-1`).
The year is the year of signature.

## Regenerate

```sh
pip install -r scripts/requirements.txt
python scripts/ru_fetch.py --raw ../_raw/ru      # downloads into a cache (resumable)
python scripts/ru_convert.py --raw ../_raw/ru --out .
```

`ru_fetch.py` uses ≤ 4 concurrent connections (3 by default) with a pause between requests and
retries with exponential backoff; it identifies itself as
`LawCodex/1.0 (+https://github.com/LawCodex)`.
