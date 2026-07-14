# Plugin SDK

Plugins extend Arceus with skills, panels, or tools.

## Manifest

Use `arceus-plugin.json` or `nexus-plugin.json` during compatibility transition.

```json
{
  "name": "SQL Reviewer",
  "version": "0.1.0",
  "type": "agent_skill",
  "entry": "plugin.py",
  "description": "Adds /sql-review",
  "permissions": ["files:read", "agent:tool"]
}
```

## Types

- `agent_skill`: adds a chat skill command.
- `panel`: adds a workspace panel.
- `tool`: adds an agent-callable tool.

## Permissions

Supported v1 permissions:

- `files:read`
- `files:write`
- `terminal:run`
- `web:fetch`
- `panel:render`
- `agent:tool`

Plugin execution sandboxing is required before arbitrary third-party plugin code can run in production.
