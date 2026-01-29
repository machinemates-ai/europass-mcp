"""Tests for the Europass MCP Server."""

import json
import pytest
from pathlib import Path

# Import the module to test
from src.mcp_server import (
    parse_document,
    create_resume,
    list_resumes,
    delete_resume,
    get_mac_schema,
    _validate_date,
    _mac_to_europass_xml,
    _resumes,
    _country_to_code,
    _phone_country_to_iso,
    _language_to_iso639b,
    _level_to_cef,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_mac_json():
    """Return a minimal valid MAC JSON structure."""
    return {
        "settings": {"language": "EN"},
        "aboutMe": {
            "profile": {
                "name": "John",
                "surnames": "Doe",
                "title": "Software Engineer",
                "description": "Experienced developer",
                "birthday": "1990-05-15",
                "location": {
                    "country": "France",
                    "region": "Île-de-France",
                    "municipality": "Paris"
                }
            },
            "relevantLinks": [
                {"type": "github", "URL": "https://github.com/johndoe"}
            ]
        },
        "careerPreferences": {
            "contact": {
                "contactMails": ["john@example.com"],
                "phoneNumbers": ["+33612345678"]
            }
        },
        "experience": {
            "jobs": [
                {
                    "organization": {
                        "name": "Tech Corp",
                        "location": {"country": "France", "municipality": "Paris"}
                    },
                    "roles": [{
                        "name": "Senior Developer",
                        "startDate": "2020-01",
                        "finishDate": "2024-12",
                        "challenges": [
                            {"description": "Led team of 5 developers"}
                        ]
                    }]
                }
            ]
        },
        "knowledge": {
            "languages": [
                {"name": "English", "fullName": "English", "level": "Native or bilingual proficiency"},
                {"name": "French", "fullName": "French", "level": "Full professional proficiency"}
            ],
            "hardSkills": [
                {"skill": {"name": "Python"}, "level": "expert"},
                {"skill": {"name": "JavaScript"}, "level": "high"}
            ],
            "softSkills": [
                {"skill": {"name": "Leadership"}},
                {"skill": {"name": "Communication"}}
            ],
            "studies": [
                {
                    "studyType": "officialDegree",
                    "degreeAchieved": True,
                    "name": "Computer Science",
                    "startDate": "2008-09",
                    "finishDate": "2012-06",
                    "institution": {
                        "name": "University of Paris",
                        "location": {"country": "France", "municipality": "Paris"}
                    }
                }
            ]
        }
    }


@pytest.fixture(autouse=True)
def clear_resumes():
    """Clear the resumes dict before and after each test."""
    _resumes.clear()
    yield
    _resumes.clear()


# ============================================================================
# Tests for _validate_date
# ============================================================================

class TestValidateDate:
    """Tests for the _validate_date helper function."""

    def test_valid_yyyy_mm(self):
        """Test YYYY-MM format."""
        assert _validate_date("2024-01") == "2024-01"
        assert _validate_date("2020-12") == "2020-12"

    def test_valid_yyyy_mm_dd(self):
        """Test YYYY-MM-DD format (should extract YYYY-MM)."""
        assert _validate_date("2024-01-15") == "2024-01"
        assert _validate_date("2020-12-31") == "2020-12"

    def test_valid_yyyy_slash_mm(self):
        """Test YYYY/MM format."""
        assert _validate_date("2024/01") == "2024-01"
        assert _validate_date("2020/12") == "2020-12"

    def test_valid_mm_yyyy(self):
        """Test MM/YYYY format (should convert to YYYY-MM)."""
        assert _validate_date("01/2024") == "2024-01"
        assert _validate_date("12/2020") == "2020-12"

    def test_valid_yyyy_only(self):
        """Test YYYY format (should append -01)."""
        assert _validate_date("2024") == "2024-01"
        assert _validate_date("2020") == "2020-01"

    def test_invalid_date(self):
        """Test invalid date formats return empty string."""
        assert _validate_date("invalid") == ""
        assert _validate_date("") == ""
        assert _validate_date("abc-def") == ""

    def test_empty_and_none(self):
        """Test empty string and edge cases."""
        assert _validate_date("") == ""
        assert _validate_date("   ") == ""


# ============================================================================
# Tests for create_resume
# ============================================================================

class TestCreateResume:
    """Tests for the create_resume function."""

    def test_create_resume_success(self, sample_mac_json):
        """Test successful resume creation."""
        result = create_resume(mac_json=sample_mac_json)
        
        assert result["status"] == "success"
        assert "resume_id" in result
        assert len(result["resume_id"]) == 8
        assert result["summary"]["name"] == "John Doe"
        assert result["summary"]["title"] == "Software Engineer"
        assert result["summary"]["jobs_count"] == 1
        assert result["summary"]["location"] == "Paris"

    def test_create_resume_missing_name(self):
        """Test error when name is missing."""
        mac_json = {
            "aboutMe": {
                "profile": {
                    "surnames": "Doe"
                }
            }
        }
        result = create_resume(mac_json=mac_json)
        
        assert result["status"] == "error"
        assert "name" in result["message"].lower()

    def test_create_resume_missing_surnames(self):
        """Test error when surnames is missing."""
        mac_json = {
            "aboutMe": {
                "profile": {
                    "name": "John"
                }
            }
        }
        result = create_resume(mac_json=mac_json)
        
        assert result["status"] == "error"
        assert "surnames" in result["message"].lower()

    def test_create_multiple_resumes(self, sample_mac_json):
        """Test creating multiple resumes."""
        result1 = create_resume(mac_json=sample_mac_json)
        
        # Modify for second resume
        sample_mac_json["aboutMe"]["profile"]["name"] = "Jane"
        result2 = create_resume(mac_json=sample_mac_json)
        
        assert result1["resume_id"] != result2["resume_id"]
        assert len(_resumes) == 2


# ============================================================================
# Tests for list_resumes
# ============================================================================

class TestListResumes:
    """Tests for the list_resumes function."""

    def test_list_empty(self):
        """Test listing when no resumes exist."""
        result = list_resumes()
        
        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["resumes"] == []

    def test_list_with_resumes(self, sample_mac_json):
        """Test listing with existing resumes."""
        create_resume(mac_json=sample_mac_json)
        
        result = list_resumes()
        
        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["resumes"][0]["name"] == "John Doe"


# ============================================================================
# Tests for delete_resume
# ============================================================================

class TestDeleteResume:
    """Tests for the delete_resume function."""

    def test_delete_existing(self, sample_mac_json):
        """Test deleting an existing resume."""
        create_result = create_resume(mac_json=sample_mac_json)
        resume_id = create_result["resume_id"]
        
        delete_result = delete_resume(resume_id=resume_id)
        
        assert delete_result["status"] == "success"
        assert resume_id in delete_result["message"]
        assert delete_result["remaining_count"] == 0

    def test_delete_nonexistent(self):
        """Test deleting a non-existent resume."""
        result = delete_resume(resume_id="nonexistent")
        
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


# ============================================================================
# Tests for get_mac_schema
# ============================================================================

class TestGetMacSchema:
    """Tests for the get_mac_schema function."""

    def test_get_schema(self):
        """Test getting the MAC schema."""
        result = get_mac_schema()
        
        # get_mac_schema returns schema info with sections
        assert "schema_url" in result
        assert "version" in result
        assert "sections" in result
        assert "example_minimal" in result


# ============================================================================
# Tests for _mac_to_europass_xml
# ============================================================================

class TestMacToEuropassXml:
    """Tests for the MAC to Europass XML conversion."""

    def test_xml_generation(self, sample_mac_json):
        """Test that XML is generated with correct structure."""
        xml = _mac_to_europass_xml(sample_mac_json)
        
        # Check XML declaration
        assert '<?xml version="1.0" encoding="utf-8"?>' in xml
        
        # Check root element
        assert "<Candidate" in xml
        assert "</Candidate>" in xml
        
        # Check personal info (uses oa:GivenName and hr:FamilyName)
        assert "<oa:GivenName>John</oa:GivenName>" in xml
        assert "<hr:FamilyName>Doe</hr:FamilyName>" in xml
        
        # Check contact info
        assert "john@example.com" in xml

    def test_xml_escapes_special_chars(self):
        """Test that special characters are properly escaped."""
        mac = {
            "settings": {"language": "EN"},
            "aboutMe": {
                "profile": {
                    "name": "John & Jane",
                    "surnames": "O'Brien <Junior>",
                }
            }
        }
        
        xml = _mac_to_europass_xml(mac)
        
        # Check XML escaping (& and < > are escaped, apostrophe is optional)
        # Note: PersonTitle/PersonDescription are NOT generated (not supported by Europass)
        assert "John &amp; Jane" in xml
        assert "O'Brien &lt;Junior&gt;" in xml  # apostrophe is valid in XML

    def test_xml_with_employment(self, sample_mac_json):
        """Test XML generation with employment history."""
        xml = _mac_to_europass_xml(sample_mac_json)
        
        assert "EmploymentHistory" in xml
        assert "Tech Corp" in xml
        assert "Senior Developer" in xml
        assert "2020-01" in xml

    def test_xml_with_education(self, sample_mac_json):
        """Test XML generation with education history."""
        xml = _mac_to_europass_xml(sample_mac_json)
        
        assert "EducationHistory" in xml
        assert "Computer Science" in xml
        assert "University of Paris" in xml

    def test_xml_with_languages(self, sample_mac_json):
        """Test XML generation with language skills."""
        xml = _mac_to_europass_xml(sample_mac_json)
        
        # Languages are in PersonCompetency with TaxonomyID=language
        assert "PersonCompetency" in xml
        assert "language" in xml  # TaxonomyID
        assert "CEF-" in xml  # CEF language level dimensions

    def test_xml_with_skills(self, sample_mac_json):
        """Test XML generation with hard and soft skills."""
        xml = _mac_to_europass_xml(sample_mac_json)
        
        assert "PersonQualifications" in xml
        assert "Python" in xml
        assert "Leadership" in xml

    def test_xml_with_full_description(self):
        """Test that fullDescription is used over challenges."""
        mac = {
            "settings": {"language": "EN"},
            "aboutMe": {
                "profile": {"name": "Jane", "surnames": "Smith"}
            },
            "experience": {
                "jobs": [{
                    "organization": {"name": "Acme Inc"},
                    "roles": [{
                        "name": "Engineer",
                        "startDate": "2022-01",
                        "challenges": [{"description": "Short bullet"}],
                        "fullDescription": "<p><strong>Contexte :</strong> Rich HTML content with full details.</p>"
                    }]
                }]
            }
        }
        
        xml = _mac_to_europass_xml(mac)
        
        # fullDescription should be used instead of challenges
        assert "Contexte :" in xml
        assert "Rich HTML content" in xml
        # challenges short text should NOT appear since fullDescription takes precedence
        assert "Short bullet" not in xml

    def test_xml_with_full_description_fallback_to_challenges(self):
        """Test that challenges are used when fullDescription is missing."""
        mac = {
            "settings": {"language": "EN"},
            "aboutMe": {
                "profile": {"name": "Jane", "surnames": "Smith"}
            },
            "experience": {
                "jobs": [{
                    "organization": {"name": "Acme Inc"},
                    "roles": [{
                        "name": "Engineer",
                        "startDate": "2022-01",
                        "challenges": [{"description": "Fallback bullet point"}]
                        # No fullDescription field
                    }]
                }]
            }
        }
        
        xml = _mac_to_europass_xml(mac)
        
        # challenges should be used as fallback
        assert "Fallback bullet point" in xml

    def test_xml_with_profile_picture(self):
        """Test that profilePicture generates Attachment XML."""
        # Use a small base64 string for testing (1x1 red pixel PNG)
        test_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        
        mac = {
            "settings": {"language": "EN"},
            "aboutMe": {
                "profile": {"name": "Jane", "surnames": "Smith"}
            },
            "profilePicture": test_base64
        }
        
        xml = _mac_to_europass_xml(mac)
        
        # Check Attachment structure
        assert "<eures:Attachment>" in xml
        assert f"<oa:EmbeddedData>{test_base64}</oa:EmbeddedData>" in xml
        assert "<oa:FileType>photo</oa:FileType>" in xml
        assert "<hr:Instructions>ProfilePicture</hr:Instructions>" in xml
        assert "</eures:Attachment>" in xml

    def test_xml_without_profile_picture(self):
        """Test that no Attachment is generated when profilePicture is missing."""
        mac = {
            "settings": {"language": "EN"},
            "aboutMe": {
                "profile": {"name": "Jane", "surnames": "Smith"}
            }
            # No profilePicture field
        }
        
        xml = _mac_to_europass_xml(mac)
        
        # Should NOT have Attachment section
        assert "<eures:Attachment>" not in xml
        assert "<oa:EmbeddedData>" not in xml


# ============================================================================
# Tests for parse_document
# ============================================================================

class TestParseDocument:
    """Tests for the parse_document function."""

    def test_file_not_found(self):
        """Test error when file doesn't exist."""
        result = parse_document("/nonexistent/path/file.pdf")
        
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_path_is_directory(self, tmp_path):
        """Test error when path is a directory."""
        result = parse_document(str(tmp_path))
        
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "not a file" in result["message"].lower()

    def test_parse_text_file(self, tmp_path):
        """Test parsing a simple text file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        
        result = parse_document(str(test_file))
        
        # markitdown returns text content
        assert isinstance(result, str)
        assert "Hello" in result


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for the full workflow."""

    def test_create_list_delete_workflow(self, sample_mac_json):
        """Test the full create -> list -> delete workflow."""
        # Create
        create_result = create_resume(mac_json=sample_mac_json)
        assert create_result["status"] == "success"
        resume_id = create_result["resume_id"]
        
        # List
        list_result = list_resumes()
        assert list_result["count"] == 1
        assert list_result["resumes"][0]["resume_id"] == resume_id
        
        # Delete
        delete_result = delete_resume(resume_id=resume_id)
        assert delete_result["status"] == "success"
        
        # Verify deleted
        list_result = list_resumes()
        assert list_result["count"] == 0

    def test_lru_cleanup(self, sample_mac_json):
        """Test that old resumes are cleaned up when max is reached."""
        from src.mcp_server import _MAX_RESUMES
        
        # Create more than max resumes
        for i in range(_MAX_RESUMES + 5):
            sample_mac_json["aboutMe"]["profile"]["name"] = f"User{i}"
            create_resume(mac_json=sample_mac_json)
        
        # Should be at max capacity
        assert len(_resumes) == _MAX_RESUMES


# ============================================================================
# Country Code Conversion Tests
# ============================================================================

class TestCountryToCode:
    """Tests for _country_to_code function."""
    
    def test_country_name_to_code(self):
        """Test country name to code conversion."""
        assert _country_to_code("France") == "fr"
        assert _country_to_code("france") == "fr"
        assert _country_to_code("FRANCE") == "fr"
        assert _country_to_code("United States") == "us"
        assert _country_to_code("Germany") == "de"
    
    def test_country_code_passthrough(self):
        """Test 2-letter codes are returned lowercase."""
        assert _country_to_code("FR") == "fr"
        assert _country_to_code("fr") == "fr"
        assert _country_to_code("US") == "us"
    
    def test_empty_country(self):
        """Test empty input returns empty string."""
        assert _country_to_code("") == ""
        assert _country_to_code("  ") == ""


class TestPhoneCountryToIso:
    """Tests for _phone_country_to_iso function."""
    
    def test_common_country_codes(self):
        """Test phone dialing codes to ISO codes."""
        assert _phone_country_to_iso("33") == "fr"
        assert _phone_country_to_iso("1") == "us"
        assert _phone_country_to_iso("44") == "gb"
        assert _phone_country_to_iso("49") == "de"
    
    def test_unknown_code(self):
        """Test unknown codes return empty string."""
        assert _phone_country_to_iso("999") == ""
        assert _phone_country_to_iso("") == ""


class TestLanguageToIso639b:
    """Tests for _language_to_iso639b function."""
    
    def test_english_variations(self):
        """Test English language name variations."""
        assert _language_to_iso639b("English") == "eng"
        assert _language_to_iso639b("english") == "eng"
        assert _language_to_iso639b("eng") == "eng"
        assert _language_to_iso639b("en") == "eng"
    
    def test_french_variations(self):
        """Test French language name variations."""
        assert _language_to_iso639b("French") == "fre"
        assert _language_to_iso639b("français") == "fre"
        assert _language_to_iso639b("fra") == "fre"
        assert _language_to_iso639b("fr") == "fre"
    
    def test_german_variations(self):
        """Test German uses ISO 639-2/B code 'ger' not 'deu'."""
        assert _language_to_iso639b("German") == "ger"
        assert _language_to_iso639b("deutsch") == "ger"
    
    def test_unknown_language(self):
        """Test unknown language returns first 3 chars."""
        assert _language_to_iso639b("Klingon") == "kli"
        assert _language_to_iso639b("") == ""


class TestLevelToCef:
    """Tests for _level_to_cef function."""
    
    def test_cef_levels(self):
        """Test CEF level mapping."""
        assert _level_to_cef("native") == "C2"
        assert _level_to_cef("Full professional proficiency") == "C2"
        assert _level_to_cef("professional working") == "C1"  # Contains "professional"
        assert _level_to_cef("limited working") == "B2"
        assert _level_to_cef("intermediate") == "B2"
        assert _level_to_cef("elementary") == "A2"
        assert _level_to_cef("basic") == "A2"
        assert _level_to_cef("unknown") == "B1"  # Default fallback
