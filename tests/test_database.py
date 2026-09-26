from datetime import date

from src.storage.database import Database


def _tournament(name: str) -> dict:
    return {
        "name": name,
        "category": "U20",
        "gender": "Women",
        "location": "Testlocatie",
        "start_date": date(2026, 8, 25),
    }


def test_memory_database_keeps_data_within_one_session_instance():
    database = Database()
    tournament_id = database.create_tournament(_tournament("Sessie A"))

    assert database.get_tournament(tournament_id)["name"] == "Sessie A"
    assert database.get_tournaments()[0]["id"] == tournament_id

    database.close()


def test_memory_databases_are_isolated_between_sessions():
    first_session = Database()
    second_session = Database()
    first_session.create_tournament(_tournament("Alleen eerste sessie"))

    assert len(first_session.get_tournaments()) == 1
    assert second_session.get_tournaments() == []

    first_session.close()
    second_session.close()
