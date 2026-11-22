import re
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict

# Control character pattern (newlines, tabs, null bytes, etc.)
CONTROL_CHARS_REGEX = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def validate_url_string(v: str) -> str:
    if not v or not isinstance(v, str):
        raise ValueError("URL cannot be empty")

    # 1. Check for control characters before whitespace trimming
    if CONTROL_CHARS_REGEX.search(v):
        raise ValueError("URL contains prohibited control characters")

    # 2. Trim whitespace
    cleaned = v.strip()
    if not cleaned:
        raise ValueError("URL cannot be empty or only whitespace")

    # 3. Reject backslash variants (e.g. http:\\evil.com)
    if "\\" in cleaned:
        raise ValueError("URL contains invalid backslashes")

    # 4. Reject scheme-relative URLs (e.g. //evil.com)
    if cleaned.startswith("//"):
        raise ValueError("Scheme-relative URLs are prohibited")

    # 5. Reject URL-encoded scheme variants or encoded slashes before parsing
    lower_cleaned = cleaned.lower()
    if "%2f" in lower_cleaned or "%3a" in lower_cleaned:
        raise ValueError("URL contains prohibited encoded scheme or slashes")

    # 6. Parse URL
    try:
        parsed = urllib.parse.urlsplit(cleaned)
    except Exception as e:
        raise ValueError(f"Invalid URL structure: {e}")

    # 7. Check scheme allowlist (http, https only) case-insensitively
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Invalid or prohibited URL scheme '{parsed.scheme}'. Only 'http' and 'https' are allowed.")

    # 8. Must have a valid network location (hostname)
    if not parsed.netloc or not parsed.hostname:
        raise ValueError("URL must include a valid hostname/domain")

    return cleaned


def validate_future_datetime(v: Optional[datetime]) -> Optional[datetime]:
    if v is not None:
        now = datetime.now(timezone.utc)
        v_normalized = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        if v_normalized <= now:
            raise ValueError("expires_at must be in the future")
        return v_normalized
    return None


def validate_tags_list(v: Optional[List[str]]) -> Optional[List[str]]:
    if v is not None:
        if len(v) > 10:
            raise ValueError("Cannot provide more than 10 tags")
        cleaned_tags = []
        for tag in v:
            if not tag or len(tag.strip()) == 0:
                continue
            if CONTROL_CHARS_REGEX.search(tag):
                raise ValueError("Tag contains prohibited control characters")
            tag_str = tag.strip()
            if len(tag_str) > 30:
                raise ValueError(f"Tag '{tag_str[:15]}...' exceeds maximum length of 30 characters")
            cleaned_tags.append(tag_str)
        return cleaned_tags
    return v


class LinkCreate(BaseModel):
    long_url: str = Field(..., description="Target destination URL")
    expires_at: Optional[datetime] = Field(default=None, description="Optional future expiry time")
    tags: Optional[List[str]] = Field(default=None, description="Optional tags")
    # Module 10: Backward-compatible optional new attributes
    title: Optional[str] = Field(default=None, max_length=255, description="Optional human-readable title")
    is_active: Optional[bool] = Field(default=True, description="Whether the link is active")

    @field_validator("long_url")
    @classmethod
    def validate_long_url(cls, v: str) -> str:
        return validate_url_string(v)

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        return validate_future_datetime(v)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return validate_tags_list(v)


class LinkUpdate(BaseModel):
    long_url: Optional[str] = Field(default=None, description="Updated target destination URL")
    expires_at: Optional[datetime] = Field(default=None, description="Optional future expiry time")
    tags: Optional[List[str]] = Field(default=None, description="Optional tags")
    title: Optional[str] = Field(default=None, max_length=255, description="Updated link title")
    is_active: Optional[bool] = Field(default=None, description="Updated link active status")

    @field_validator("long_url")
    @classmethod
    def validate_long_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_url_string(v)
        return v

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        return validate_future_datetime(v)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return validate_tags_list(v)


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    short_url: str
    long_url: str
    created_by: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    tags: Optional[str] = None
    # Backward-compatible response fields
    title: Optional[str] = None
    is_active: Optional[bool] = True


class LinkAnalyticsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    link_id: int
    from_date: str = Field(..., alias="from", serialization_alias="from")
    to_date: str = Field(..., alias="to", serialization_alias="to")
    total_clicks: int
    last_clicked_at: Optional[datetime] = None


class BatchAnalyticsItem(BaseModel):
    link_id: int
    total_clicks: int
    last_clicked_at: Optional[datetime] = None


class BatchAnalyticsResponse(BaseModel):
    items: List[BatchAnalyticsItem]
    total_links_queried: int
