# CloudBank modern Oracle reference estate

This directory records an inventory-only acquisition of Oracle's official CloudBank v5 reference
application from `oracle/microservices-backend`. The upstream source is pinned at commit
`4f41b16d00c45503f691836fee8138010c969e86`; its source code is not copied into this repository.

CloudBank is important because it is already a cloud-native microservices application while still
depending on Oracle Database, Oracle connection and wallet components, Transactional Event Queue,
and Oracle MicroTx LRA coordination. It lets LIGHTYEAR demonstrate that autonomous modernization
is not limited to visibly old applications: a modern Java/Kubernetes estate can also require
database decoupling and behavioral verification.

## Measured source surface

The pinned `cloudbank-v5` subtree contains:

- 189 tracked files;
- 70 Java source units and 6,711 Java source lines;
- 10 Maven modules, eight runtime service modules, and ten deployable units;
- nine SQL files and 231 SQL lines;
- 53 Spring and nine JAX-RS endpoint annotations; and
- static Oracle, LRA, local-transaction, messaging, and security coupling signals.

The Control Tower exposes five workloads and 20 bounded migration-risk scenarios:

1. customer and account management;
2. money transfer;
3. cheque deposit and clearance;
4. authentication and service authorization; and
5. credit score service.

## Rebuild the inventory

```bash
git clone --filter=blob:none --no-tags \
  https://github.com/oracle/microservices-backend.git /path/to/oracle-microservices-backend
git -C /path/to/oracle-microservices-backend checkout \
  4f41b16d00c45503f691836fee8138010c969e86
./cloudbank-reference-estate.sh inventory /path/to/oracle-microservices-backend
./cloudbank-reference-estate.sh verify-inventory /path/to/oracle-microservices-backend
./cloudbank-reference-estate.sh build
./cloudbank-reference-estate.sh verify
```

Windows:

```powershell
.\cloudbank-reference-estate.ps1 inventory C:\path\to\oracle-microservices-backend
.\cloudbank-reference-estate.ps1 verify-inventory C:\path\to\oracle-microservices-backend
.\cloudbank-reference-estate.ps1 build
.\cloudbank-reference-estate.ps1 verify
```

The inventory tool refuses a dirty checkout or a commit other than the recorded pin.

## Control Tower projection

**CloudBank Reference Estate** is selectable alongside **CardDemo Reference Estate** and
**Oracle Customer (Large)**. It is a source estate for future autonomous Oracle-to-PostgreSQL or
other adapter-qualified relational-target work. The database scope is recommended, but target
selection remains a governed later decision.

The projection is composed with the existing PL/I and Oracle Customer (Large) fragments. It does
not change the canonical CardDemo graph or the identity to which runtime and audit evidence are
bound.

## Evidence boundary

This milestone is upstream static inventory and curated migration-risk evidence. CloudBank was not
built or executed. No customer system is attached. No PostgreSQL mapping, alternative-target
mapping, generated refactoring, native target execution, application equivalence, migration
completion, or production readiness is claimed. Those capabilities require later transformation
and dual-run evidence milestones.
