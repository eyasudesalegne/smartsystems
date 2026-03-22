from app.connectors import catalog_rows_for_sync, get_connector, render_n8n_workflow


def test_pubmed_connector_exists():
    spec = get_connector('pubmed')
    assert spec['service_name'] == 'pubmed'
    assert spec['operations']


def test_render_workflow_has_name():
    wf = render_n8n_workflow('pubmed', 'search')
    assert wf['name'].startswith('wf_ext_pubmed_')


def test_catalog_rows_for_sync_contains_all_services():
    rows = catalog_rows_for_sync('default')
    assert len(rows) >= 14
    assert any(row['service_name'] == 'mlflow' for row in rows)
    assert all(row['tenant_id'] == 'default' for row in rows)
