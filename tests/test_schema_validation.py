#!/usr/bin/env python3
"""
Schema validation tests for MAC JSON.

Ensures generated output conforms to expected schemas.
"""

import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestMACSchema:
    """Validate MAC JSON structure."""

    def test_mac_schema_required_fields(self):
        """MAC JSON must have required top-level fields."""
        from mac_schema import extracted_cv_to_mac, ExtractedCV, ExtractedJob
        
        # Minimal valid CV with correct field names
        cv = ExtractedCV(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            jobs=[
                ExtractedJob(
                    company_name="Test Corp",
                    job_title="Developer",
                    start_date="2024-01",
                    description="Built things",
                )
            ],
        )
        
        mac = extracted_cv_to_mac(cv)
        
        # Required fields
        assert "$schema" in mac
        assert "settings" in mac
        assert "aboutMe" in mac
        assert "experience" in mac
        assert "knowledge" in mac
        
    def test_mac_job_structure(self):
        """Job entries must have correct structure."""
        from mac_schema import extracted_cv_to_mac, ExtractedCV, ExtractedJob
        
        cv = ExtractedCV(
            first_name="Test",
            last_name="User",
            jobs=[
                ExtractedJob(
                    company_name="Acme Inc",
                    job_title="Senior Developer",
                    location="Paris, France",
                    start_date="2024-01",
                    end_date="2025-01",
                    description="- Built API\n- Deployed",
                )
            ],
        )
        
        mac = extracted_cv_to_mac(cv)
        jobs = mac["experience"]["jobs"]
        
        assert len(jobs) == 1
        job = jobs[0]
        
        # Organization
        assert "organization" in job
        assert job["organization"]["name"] == "Acme Inc"
        
        # Roles
        assert "roles" in job
        assert len(job["roles"]) == 1
        role = job["roles"][0]
        
        assert role["name"] == "Senior Developer"
        assert "startDate" in role
        assert "challenges" in role

    def test_mac_dates_iso_format(self):
        """Dates must be in ISO format."""
        from mac_schema import extracted_cv_to_mac, ExtractedCV, ExtractedJob
        
        cv = ExtractedCV(
            first_name="Test",
            last_name="User",
            jobs=[
                ExtractedJob(
                    company_name="Test",
                    job_title="Dev",
                    start_date="2024-01-15",
                    end_date="2025-06",
                    description="Work",
                )
            ],
        )
        
        mac = extracted_cv_to_mac(cv)
        role = mac["experience"]["jobs"][0]["roles"][0]
        
        # Dates should be valid ISO format
        import re
        date_pattern = r'^\d{4}-\d{2}(-\d{2})?$'
        assert re.match(date_pattern, role["startDate"])
        if role.get("finishDate"):
            assert re.match(date_pattern, role["finishDate"])

    def test_description_transform_applied(self):
        """Descriptions should have AST transform applied."""
        from mac_schema import extracted_cv_to_mac, ExtractedCV, ExtractedJob
        
        # Input with H2 heading format
        cv = ExtractedCV(
            first_name="Test",
            last_name="User",
            jobs=[
                ExtractedJob(
                    company_name="Test",
                    job_title="Dev",
                    start_date="2024-01",
                    description="## Achievements\n- Built API\n- Deployed",
                )
            ],
        )
        
        mac = extracted_cv_to_mac(cv)
        challenge = mac["experience"]["jobs"][0]["roles"][0]["challenges"][0]
        desc = challenge["description"]
        
        # H2 should be converted to bullet parent
        assert "## Achievements" not in desc
        assert "- **Achievements**" in desc
        # Items should be nested
        assert "  - Built API" in desc


class TestDescriptionPreservation:
    """Test that descriptions preserve content through pipeline."""

    def test_bold_preserved(self):
        """Bold formatting should be preserved."""
        from mac_schema import extracted_cv_to_mac, ExtractedCV, ExtractedJob
        
        cv = ExtractedCV(
            first_name="Test",
            last_name="User",
            jobs=[
                ExtractedJob(
                    company_name="Test",
                    job_title="Dev",
                    start_date="2024-01",
                    description="- Built **FastAPI** backend",
                )
            ],
        )
        
        mac = extracted_cv_to_mac(cv)
        desc = mac["experience"]["jobs"][0]["roles"][0]["challenges"][0]["description"]
        assert "**FastAPI**" in desc

    def test_links_preserved(self):
        """Link formatting should be preserved."""
        from mac_schema import extracted_cv_to_mac, ExtractedCV, ExtractedJob
        
        cv = ExtractedCV(
            first_name="Test",
            last_name="User",
            jobs=[
                ExtractedJob(
                    company_name="Test",
                    job_title="Dev",
                    start_date="2024-01",
                    description="- [View demo](https://example.com)",
                )
            ],
        )
        
        mac = extracted_cv_to_mac(cv)
        desc = mac["experience"]["jobs"][0]["roles"][0]["challenges"][0]["description"]
        assert "[View demo](https://example.com)" in desc

    def test_unicode_preserved(self):
        """Unicode should be preserved."""
        from mac_schema import extracted_cv_to_mac, ExtractedCV, ExtractedJob
        
        cv = ExtractedCV(
            first_name="Gaëtan",
            last_name="Fortaine",
            jobs=[
                ExtractedJob(
                    company_name="Société Générale",
                    job_title="Développeur",
                    start_date="2024-01",
                    description="- Implémentation système 🚀",
                )
            ],
        )
        
        mac = extracted_cv_to_mac(cv)
        # Check name contains first name (full name format may vary)
        assert "Gaëtan" in mac["aboutMe"]["profile"]["name"]
        desc = mac["experience"]["jobs"][0]["roles"][0]["challenges"][0]["description"]
        assert "🚀" in desc


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
