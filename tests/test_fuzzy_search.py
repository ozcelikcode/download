"""Typo ranking respects publication visibility, filters and pagination."""

import pytest

from app import crud
from app.models import Download
from app.search_matching import search_score


@pytest.mark.parametrize('query', ['fggoogle', 'googlee', 'googel', 'gogle', 'GOOGLE'])
def test_typo_and_case_matches(query):
    assert search_score('Google Chrome', query) > 0


def test_unrelated_short_words_wildcards_and_large_inputs_do_not_match_everything():
    assert search_score('Google Chrome', 'Firefox') == 0
    assert search_score('Google Chrome', 'xy') == 0
    assert search_score('Google Chrome', '%_') == 0
    assert search_score('Google Chrome', 'x' * 10000) == 0
    assert search_score('İndirme Arşivi', 'indirme arsivi') == 100
    assert search_score('Google Chrome', 'google') > search_score('Google Chrome', 'googel')


async def test_fuzzy_results_are_filtered_and_ranked_before_pagination(client, db_session):
    db_session.add_all([
        Download(title='Google Chrome', slug='google-chrome', external_url='https://example.com'),
        Download(title='Googel tool', slug='googel-tool', external_url='https://example.com'),
        Download(title='Private Google', slug='private-google', is_hidden=True),
        Download(title='Draft Google', slug='draft-google', is_draft=True),
    ])
    await db_session.commit()
    items, total = await crud.get_downloads_paginated(db_session, search='googel', page_size=1)
    assert total == 2 and items[0].slug == 'googel-tool'
    items, total = await crud.get_downloads_paginated(db_session, search='googel', page=2, page_size=1)
    assert total == 2 and items[0].slug == 'google-chrome'
    response = await client.get('/search', params={'q': 'fggoogle'})
    assert response.status_code == 200 and 'Google Chrome' in response.text
    assert 'Private Google' not in response.text and 'Draft Google' not in response.text
    assert (await client.get('/search', params={'q': 'x' * 201})).status_code == 422
