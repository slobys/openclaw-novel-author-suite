# Upgrade to 0.4.4

0.4.4 packages Novel Engine together with the Novel Author V5.3.2 workspace for public one-click deployment.

Default writing contract for newly created projects:

- hard minimum: 2000 Han characters;
- preferred target: 2600 Han characters;
- preferred upper bound: 3200 Han characters.

Existing projects keep their saved `project-config.json`. Update an existing project through `novel_project_config_read` plus revision-bound `novel_project_configure` when you want the new range.

No project data migration is required from 0.4.3.
