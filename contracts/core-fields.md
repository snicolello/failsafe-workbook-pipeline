# What a served row promises

Each row describes one item's current milestone in one source tab. Sedgewater Outfitters and its nine brands are fictional. The source team supplies five fields.

| Field | Accepted representation |
| --- | --- |
| `item_ref` | Nonempty text, unique within the brand and worksheet |
| `season` | Nonempty assortment season |
| `stage` | A member of the profile's governed stage vocabulary |
| `target_date` | Excel calendar date or ISO date, emitted as YYYY-MM-DD |
| `owner` | Nonempty fictional team or owner |

Each row carries the original workbook's SHA-256, brand, worksheet and a source locator for every field. A worksheet title can itself supply a field. Header aliases belong to one brand. Whitespace and case normalization for header matching leave the original workbook untouched.

A whole tab passes together. A failed attempt records its evidence and leaves the prior accepted rows available with their acceptance time. A first-time failure serves zero rows. The report promises only that every served row passed the declared contract. A plausible but incorrect date supplied by a source team can pass validation.
