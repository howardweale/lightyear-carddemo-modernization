# Security and operations deployment guide

## Intake boundary

Place customer source in a dedicated, access-controlled directory. The pilot reads files without
modifying them and rejects symbolic links, hidden paths, unsupported extensions, binary/NUL content,
oversized files or trees, and credential-shaped strings. The graph and dossier record only bounded
paths, types, relationships, metadata, and hashes; they do not embed source text.

Use a customer-issued approval identifier that can be mapped to the external authorization record.
The identifier is not itself proof of legal authorization; operators must retain that approval in
the customer's governance system.

## Runtime boundary

- Run as an unprivileged account.
- Keep the source directory read-only.
- Write generated evidence to a separate directory.
- Do not supply mainframe, database, cloud, or model credentials to the source-only command.
- Transfer JSON/Markdown evidence through the customer's approved channel.
- Apply the customer's retention and deletion policy to source and generated output.

## Preparing later mainframe collection

Review `mainframe.preflight.json` with the mainframe custodian and independent verifier. Establish
separate identities and keys for evidence collection and equivalence signing. Configure approved
TLS endpoints, certificates, credential delivery, test data, execution scope, rollback, retention,
and incident handling before using the enterprise collection appliance.

Passing appliance fault tests proves retry, resume, redirect rejection, bounds, checkpoint integrity,
and digest-only retention mechanics. It is not customer-network accreditation or live evidence.
