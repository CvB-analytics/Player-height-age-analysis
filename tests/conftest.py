from pathlib import Path

import pytest
from reportlab.pdfgen import canvas


@pytest.fixture
def synthetic_bulletin(tmp_path: Path) -> Path:
    """Create a CEV-like bulletin containing only invented test players."""
    target = tmp_path / "synthetic_u20_bulletin.pdf"
    pdf = canvas.Canvas(str(target))
    teams = [
        ("TESTLAND ALPHA", "TAA", 14),
        ("TESTLAND BRAVO", "TBB", 14),
        ("TESTLAND CHARLIE", "TCC", 14),
        ("TESTLAND DELTA", "TDD", 14),
        ("TESTLAND ECHO", "TEE", 12),
        ("TESTLAND FOXTROT", "TFF", 14),
    ]
    positions = ["Libero", "Setter", "Outside spiker", "Middle blocker", "Opposite"]
    for team_index, (country, code, player_count) in enumerate(teams):
        y = 800
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(45, y, f"{country} ({code})")
        y -= 22
        pdf.drawString(45, y, "FINAL TEAM LIST AND DELEGATION")
        y -= 18
        pdf.setFont("Helvetica", 8)
        pdf.drawString(45, y, "No Name & First Name Position BIRTH DATE Weight Height Reach Last Club")
        y -= 16
        for player_index in range(player_count):
            jersey = player_index + 1
            surname = f"TESTSURNAME{team_index + 1}{player_index + 1}"
            first_name = f"Player{team_index + 1}{player_index + 1}"
            position = positions[player_index % len(positions)]
            day = (player_index % 27) + 1
            month = (player_index % 12) + 1
            year = 8 + (player_index % 3)
            height = 164 + team_index * 3 + (player_index % 8)
            line = (
                f"{jersey} {surname} {first_name} {position} "
                f"{day:02d}/{month:02d}/{year:02d} 60 {height} 230 300 Test Club ({code})"
            )
            pdf.drawString(45, y, line)
            y -= 15
        pdf.drawString(45, y, "TEAM OFFICIAL")
        pdf.showPage()
    pdf.save()
    return target
