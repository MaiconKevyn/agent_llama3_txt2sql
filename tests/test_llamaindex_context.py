from src.agent.llamaindex_context import (
    LLAMAINDEX_MODE_CONTEXT,
    SimpleSchemaDocument,
    build_llamaindex_schema_documents,
    normalize_llamaindex_mode,
    retrieve_llamaindex_schema_context,
    should_use_llamaindex_context,
    should_use_llamaindex_sql_draft,
)


def test_llamaindex_mode_aliases_are_normalized():
    assert normalize_llamaindex_mode("llamaindex_context") == LLAMAINDEX_MODE_CONTEXT
    assert normalize_llamaindex_mode("context") == LLAMAINDEX_MODE_CONTEXT
    assert normalize_llamaindex_mode(None) == "current"


def test_llamaindex_feature_flags_enable_context_and_sql_draft():
    assert should_use_llamaindex_context({"llamaindex_mode": "context"})
    assert should_use_llamaindex_context({"enable_llamaindex_context": True})
    assert should_use_llamaindex_context({"llamaindex_mode": "sql_draft"})
    assert should_use_llamaindex_sql_draft({"llamaindex_mode": "sql_draft"})
    assert should_use_llamaindex_sql_draft({"enable_llamaindex_sql_draft": True})
    assert not should_use_llamaindex_sql_draft({"llamaindex_mode": "hybrid"})


def test_build_llamaindex_schema_documents_contains_domain_context():
    docs = build_llamaindex_schema_documents(["internacoes", "municipios"])

    assert len(docs) == 2
    assert all(isinstance(doc, SimpleSchemaDocument) or hasattr(doc, "metadata") for doc in docs)
    contents = "\n".join(doc.get_content() for doc in docs if hasattr(doc, "get_content"))
    assert "internacoes" in contents
    assert "MORTE" in contents
    assert "municipios" in contents


def test_build_llamaindex_schema_documents_uses_generated_schema_docs(monkeypatch, tmp_path):
    docs_dir = tmp_path / "generated"
    docs_dir.mkdir()
    (docs_dir / "table_metadata.csv").write_text(
        "schema_name,table_name,has_primary_key,estimated_size,column_count,index_count,check_constraint_count,sql\n"
        "main,internacoes,true,183,3,1,0,\n"
        "main,hospital,true,2,2,1,0,\n"
        "main,stg_shadow,false,1,1,0,0,\n",
        encoding="utf-8",
    )
    (docs_dir / "column_catalog.csv").write_text(
        "table_schema,table_name,ordinal_position,column_name,data_type,is_nullable\n"
        "main,internacoes,1,N_AIH,VARCHAR,NO\n"
        "main,internacoes,2,CNES,VARCHAR,NO\n"
        "main,internacoes,3,MORTE,BOOLEAN,NO\n"
        "main,hospital,1,CNES,VARCHAR,NO\n"
        "main,hospital,2,MUNIC_MOV,VARCHAR,YES\n"
        "main,stg_shadow,1,raw,VARCHAR,YES\n",
        encoding="utf-8",
    )
    (docs_dir / "column_profiles_exact.csv").write_text(
        "table_schema,table_name,column_name,data_type,row_count,null_count,null_rate,profile_tier,profile_mode,"
        "exact_distinct_count,approx_distinct_count,distinct_count_for_catalog,distinct_is_exact,distinct_rate,"
        "min_value,max_value,profile_seconds,profile_sql\n"
        "main,internacoes,MORTE,BOOLEAN,183,0,0.0,core,exact,2,,2,true,0.01,False,True,0.01,\n",
        encoding="utf-8",
    )
    (docs_dir / "column_profiles_approx.csv").write_text(
        "table_schema,table_name,column_name,data_type,row_count,null_count,null_rate,profile_tier,profile_mode,"
        "exact_distinct_count,approx_distinct_count,distinct_count_for_catalog,distinct_is_exact,distinct_rate,"
        "min_value,max_value,profile_seconds,profile_sql\n",
        encoding="utf-8",
    )
    (docs_dir / "join_policy.csv").write_text(
        "left,right,business_meaning,left_rows,matched_rows,unmatched_rows,match_rate_non_null,confidence,accepted_usage_policy\n"
        "internacoes.CNES,hospital.CNES,Hospital de atendimento pela chave CNES,183,183,0,1.0,confirmed,business_inner_join_allowed\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLAMAINDEX_SCHEMA_DOCS_DIR", str(docs_dir))

    docs = build_llamaindex_schema_documents(["internacoes", "hospital", "stg_shadow"])
    contents = "\n\n".join(doc.get_content() for doc in docs if hasattr(doc, "get_content"))

    assert len(docs) == 2
    assert "SOURCE: src/application/schema/generated" in contents
    assert "ROW_COUNT_ESTIMATE: 183" in contents
    assert "- MORTE: BOOLEAN" in contents
    assert "JOIN_POLICIES:" in contents
    assert "internacoes.CNES -> hospital.CNES" in contents
    assert "stg_shadow" not in contents


def test_retrieve_llamaindex_schema_context_falls_back_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = retrieve_llamaindex_schema_context(
        "Quantas mortes foram registradas?",
        ["internacoes", "municipios"],
        top_k_tables=2,
        index_dir=str(tmp_path),
    )

    assert result.selected_tables == []
    assert result.retrieval_mode == "llamaindex_unavailable"
    assert result.confidence == 0.0
