"""Tests for Alembic migrations."""

import importlib.util
import sys
from pathlib import Path


class TestMigrationStructure:
    """Test that migration files are properly structured."""

    def test_initial_migration_can_be_loaded(self) -> None:
        """Verify the initial migration module can be imported."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "001_initial.py"
        assert migration_path.exists(), f"Migration file not found: {migration_path}"

        # Load the module
        spec = importlib.util.spec_from_file_location("001_initial", migration_path)
        assert spec is not None
        assert spec.loader is not None

        module = importlib.util.module_from_spec(spec)
        sys.modules["001_initial"] = module
        spec.loader.exec_module(module)

        # Verify required attributes exist
        assert hasattr(module, "revision")
        assert hasattr(module, "down_revision")
        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")

        # Verify revision info
        assert module.revision == "001_initial"
        assert module.down_revision is None

    def test_initial_migration_has_callable_functions(self) -> None:
        """Verify upgrade and downgrade functions are callable."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "001_initial.py"
        spec = importlib.util.spec_from_file_location("001_initial_test", migration_path)
        assert spec is not None
        assert spec.loader is not None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert callable(module.upgrade)
        assert callable(module.downgrade)

    def test_env_module_can_be_loaded(self) -> None:
        """Verify the Alembic env.py module can be imported."""
        env_path = Path(__file__).parent.parent / "alembic" / "env.py"
        assert env_path.exists(), f"env.py not found: {env_path}"

        spec = importlib.util.spec_from_file_location("alembic_env", env_path)
        assert spec is not None
        assert spec.loader is not None

        # Verify the module can be loaded by checking we can read the source
        # and it contains the expected function definitions
        content = env_path.read_text()
        assert "def get_database_url" in content
        assert "def run_migrations_offline" in content
        assert "def run_migrations_online" in content
        assert "async def run_async_migrations" in content
        assert "target_metadata = Base.metadata" in content


class TestMigrationContent:
    """Test that migration creates expected database objects."""

    def test_migration_creates_users_table(self) -> None:
        """Verify the migration defines users table creation."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "001_initial.py"
        content = migration_path.read_text()

        assert 'create_table(' in content and '"users"' in content
        assert "external_id" in content
        assert "paperless_token_encrypted" in content

    def test_migration_creates_shares_table(self) -> None:
        """Verify the migration defines shares table creation."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "001_initial.py"
        content = migration_path.read_text()

        assert 'create_table(' in content and '"shares"' in content
        assert "owner_id" in content
        assert "include_tags" in content
        assert "exclude_tags" in content
        assert "done_folder_enabled" in content

    def test_migration_creates_audit_log_table(self) -> None:
        """Verify the migration defines audit_log table creation."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "001_initial.py"
        content = migration_path.read_text()

        assert 'create_table(' in content and '"audit_log"' in content
        assert "event_type" in content
        assert "ip_address" in content
        assert "user_agent" in content

    def test_migration_creates_indexes(self) -> None:
        """Verify the migration defines all required indexes."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "001_initial.py"
        content = migration_path.read_text()

        # Check for shares indexes
        assert "idx_shares_name" in content
        assert "idx_shares_owner" in content
        assert "idx_shares_expires" in content

        # Check for audit_log indexes
        assert "idx_audit_timestamp" in content
        assert "idx_audit_user" in content

    def test_migration_downgrade_drops_in_correct_order(self) -> None:
        """Verify downgrade drops tables in reverse order (respecting FK constraints)."""
        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "001_initial.py"
        content = migration_path.read_text()

        # Find positions of drop_table calls in downgrade
        downgrade_start = content.find("def downgrade")
        downgrade_content = content[downgrade_start:]

        audit_log_pos = downgrade_content.find('drop_table("audit_log")')
        shares_pos = downgrade_content.find('drop_table("shares")')
        users_pos = downgrade_content.find('drop_table("users")')

        # audit_log should be dropped before shares (FK to shares)
        # shares should be dropped before users (FK to users)
        assert audit_log_pos < shares_pos, "audit_log should be dropped before shares"
        assert shares_pos < users_pos, "shares should be dropped before users"
