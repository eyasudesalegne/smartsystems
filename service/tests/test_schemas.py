from app.schemas import GenerateRequest, ConnectorCatalogItem


def test_generate_request_defaults():
    req = GenerateRequest(prompt='hi')
    assert req.prompt_version


def test_connector_catalog_item():
    item = ConnectorCatalogItem(
        service_name='pubmed',
        display_name='PubMed',
        category='literature',
        integration_mode='rest_api',
        auth_type='query_params',
        base_url_env='PUBMED_BASE_URL',
        base_url_placeholder='{$env.PUBMED_BASE_URL}',
        implementation_status='live_api',
    )
    assert item.service_name == 'pubmed'
