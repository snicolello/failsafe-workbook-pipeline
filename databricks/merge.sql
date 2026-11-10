-- Load records and quarantine evidence before publishing the new checkpoints.
MERGE INTO accepted AS t USING incoming_accepted AS s
ON t.brand = s.brand AND t.tab = s.tab AND t.item_ref = s.item_ref
   AND t.sha = s.sha AND t.attempt_id = s.attempt_id
WHEN NOT MATCHED THEN INSERT *;

MERGE INTO quarantine AS t USING incoming_quarantine AS s
ON t.brand = s.brand AND t.tab = s.tab AND t.sha = s.sha AND t.attempt_id = s.attempt_id
WHEN NOT MATCHED THEN INSERT *;

MERGE INTO retirements AS t USING incoming_retirements AS s
ON t.brand = s.brand AND t.tab = s.tab AND t.sha = s.sha AND t.attempt_id = s.attempt_id
WHEN NOT MATCHED THEN INSERT *;

MERGE INTO checkpoints AS t USING incoming_checkpoints AS s
ON t.snapshot = s.snapshot
WHEN NOT MATCHED THEN INSERT *;
