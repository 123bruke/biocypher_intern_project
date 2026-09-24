
CALL apoc.periodic.iterate(
    "LOAD CSV WITH HEADERS FROM 'file:///emapa/edges_anatomy_is_a_anatomy.csv' AS row FIELDTERMINATOR '|' RETURN row",
    "MATCH (source:anatomy {id: row.source_id})
    MATCH (target:anatomy {id: row.target_id})
    CREATE (source)-[r:is_a]->(target)
    SET r += apoc.map.removeKeys(row, ['source_id', 'target_id', 'label', 'source_type', 'target_type'])",
    {batchSize:1000}
)
YIELD batches, total
RETURN batches, total;
