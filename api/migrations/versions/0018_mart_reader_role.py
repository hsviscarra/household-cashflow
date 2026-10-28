"""Read-only role for Claude's MCP endpoint (F18, ADR-017): mart_reader may SELECT from the mart
views and nothing else. The login that uses it (cashflow_reader) is created at start-up from a
secret, not here.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "IF DATABASE_PRINCIPAL_ID(N'mart_reader') IS NULL CREATE ROLE [mart_reader] "
        "AUTHORIZATION [dbo];"
    )
    # The views read core tables through ownership chaining (all owned by dbo), so this grant
    # is enough to query them and gives no access to the tables themselves.
    op.execute("GRANT SELECT ON SCHEMA::[mart] TO [mart_reader];")


def downgrade() -> None:
    # Members (cashflow_reader) leave the role first; the user itself stays, without access.
    # One quiet batch: rowcount messages would leave results pending on the connection.
    op.execute(
        """
SET NOCOUNT ON;
DECLARE @sql NVARCHAR(MAX) = N'';
SELECT @sql = @sql + N'ALTER ROLE [mart_reader] DROP MEMBER ' + QUOTENAME([m].[name]) + N';'
FROM [sys].[database_role_members] AS [rm]
JOIN [sys].[database_principals] AS [r] ON [r].[principal_id] = [rm].[role_principal_id]
JOIN [sys].[database_principals] AS [m] ON [m].[principal_id] = [rm].[member_principal_id]
WHERE [r].[name] = N'mart_reader';
IF @sql <> N'' EXEC (@sql);
IF DATABASE_PRINCIPAL_ID(N'mart_reader') IS NOT NULL DROP ROLE [mart_reader];
"""
    )
