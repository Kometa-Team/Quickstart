# Seerr

Seerr is an optional connector for movie and show requests. It routes requests to
the Radarr and Sonarr servers configured **inside Seerr**. Quickstart's direct
Radarr/Sonarr connections remain independent and are not required for Seerr.

Open **Seerr** in Quickstart, enter the URL and API key, and select **Validate**.
This reads the authenticated `/api/v1/auth/me` endpoint; it never creates a media
request. The API key is masked. Disabling the global connection preserves its
settings while omitting that connection from generated YAML.

The expandable optional-page guidance contains setup notes and documentation
links. Leaving Seerr incomplete or unvalidated does not block the final Kometa
page; the connection is omitted from generated YAML and its saved values are
retained. As with other optional services, enabling collection requests that
inherit the global Seerr connection makes that connection a required dependency.

On **Libraries**, expand **Seerr connection and shared requests**. Blank URL and
API key fields inherit their corresponding global values independently. Enter
either field to override it; **Restore global credentials** clears just those
two overrides. **Validate effective connection** checks the combined credentials.

Shared request options apply to the library's collection defaults. Applicable
collection defaults also have a **Seerr requests** section in their details.
Check **Override** to set a request switch explicitly; an unchecked request
switch then exports `false`. Clear **Override** to restore inheritance.

- **Request missing** requests media absent from Plex.
- **Request existing** can request media already in Plex, for example a 4K
  upgrade. Enable this deliberately.
- **Standard**, **4K**, and **Both** select the servers configured for those tiers
  in Seerr. Both sends independent requests; a failure or duplicate for one tier
  does not prevent the other attempt. Kometa requests all seasons for shows.
- **Advanced tier overrides** optionally select a positive server ID, a quality
  profile ID or name, and a root folder for each tier. Blank fields use Seerr's
  defaults. The JSON view retains additional imported values.

The individual-collection-key JSON section supports the corresponding keyed
variables, such as `seerr_add_missing_popular` or `seerr_instance_popular`.

Quickstart warns when Seerr request options and direct Radarr/Sonarr
`add_missing` are enabled together because both paths can submit requests.

For custom collection definitions, use the existing collection YAML editor:

```yaml
collections:
  Movie Requests:
    tmdb_movie: 550
    seerr_add_missing: true
    seerr_add_existing: false
    seerr_instance: both
    seerr_overrides:
      standard:
        server_id: 1
        quality_profile: HD-1080p
      4k:
        quality_profile: 4
        root_folder: /movies-4k
```

Seerr settings are imported and retained, including explicit false values and
additional fields. Unknown fields are preserved for newer runtimes; they are
still subject to Kometa's schema validation when generating YAML.

Quickstart inspects the selected managed or existing direct Kometa installation
for the Seerr connector and builder support. Unsupported or uninstalled runtimes
cannot pass generated-config validation with Seerr settings. Update or install a
compatible runtime first. In external mode, Quickstart cannot inspect the runtime;
verify that it includes Seerr support and check the confirmation on the Seerr
page. Imported settings remain stored regardless of runtime compatibility.

Connector support and defaults support are separate capabilities. Some Kometa
builds include the connector and schema but their shared `defaults/templates.yml`
does not yet forward Seerr variables. Quickstart reports this during export
validation when those variables are used. Update to compatible defaults, or use
direct Seerr attributes in custom collection YAML as shown above.

See the [Kometa Seerr documentation](https://kometa.wiki/en/develop/config/seerr/)
and [Kometa PR #3738](https://github.com/Kometa-Team/Kometa/pull/3738).
