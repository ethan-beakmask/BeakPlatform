from app.models import Organization


def test_general_settings_rejects_invalid_country(admin_client):
    response = admin_client.put(
        '/beakplatform/api/admin/settings/general',
        json={'country': 'XX'},
    )

    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_general_settings_accepts_valid_country(admin_client, test_org):
    response = admin_client.put(
        '/beakplatform/api/admin/settings/general',
        json={'country': 'JP'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['country'] == 'JP'

    org = Organization.query.filter_by(secure_code=test_org.secure_code).one()
    assert org.get_setting('country') == 'JP'
