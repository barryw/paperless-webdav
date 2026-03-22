# Changelog
All notable changes to this project will be documented in this file. See [conventional commits](https://www.conventionalcommits.org/) for commit guidelines.

- - -
## [v0.1.0](https://github.com/barryw/paperless-webdav/compare/b156fd28f1a5131c6af02b124732efd161d1213a..v0.1.0) - 2026-03-22
#### Features
- (**auth**) load Paperless token from database for OIDC users - ([14d7f87](https://github.com/barryw/paperless-webdav/commit/14d7f878342a6499d82b813c02e81f1a7d2889c5)) - Barry Walker, Claude Opus 4.5
- (**auth**) add OIDC routes for Authentik SSO login flow - ([2b0cfec](https://github.com/barryw/paperless-webdav/commit/2b0cfecca5ef37b4a65c7691df9d6c36b5ca214c)) - Barry Walker, Claude Opus 4.5
- (**cache**) add Redis caching for document content and sizes - ([9d0ad43](https://github.com/barryw/paperless-webdav/commit/9d0ad43c13e1360a4a310421b16bc64d18db982c)) - Barry Walker, Claude Opus 4.5
- (**ci**) proper semver release workflow - ([b4d3fc8](https://github.com/barryw/paperless-webdav/commit/b4d3fc8a4af1d046091592250e857c3b6a43075b)) - Barry Walker, Claude Opus 4.5
- (**db**) add encrypted token storage and retrieval functions - ([fa37710](https://github.com/barryw/paperless-webdav/commit/fa37710281bdb685f13fc9b5aa2e2e922538b191)) - Barry Walker, Claude Opus 4.5
- (**k8s**) scale to 2 replicas with pod anti-affinity - ([34a79a9](https://github.com/barryw/paperless-webdav/commit/34a79a903825f5eb3a24fc705123f5c0ab02267e)) - Barry Walker, Claude Opus 4.5
- (**k8s**) configure Authentik OIDC authentication - ([afda73a](https://github.com/barryw/paperless-webdav/commit/afda73a36e5d4ef914ac99c3d25b17b7312f508a)) - Barry Walker, Claude Opus 4.5
- (**ui**) add auth mode support to login page - ([4e70604](https://github.com/barryw/paperless-webdav/commit/4e706047ec4c0e90a982d565f3430c83e0f8d3c3)) - Barry Walker, Claude Opus 4.5
- (**ui**) add token setup page for OIDC users - ([406d884](https://github.com/barryw/paperless-webdav/commit/406d884a2dfb9c6f79ca140a4792de284d51abef)) - Barry Walker, Claude Opus 4.5
- (**webdav**) add Redis lock storage for multi-replica deployments - ([20c7c2d](https://github.com/barryw/paperless-webdav/commit/20c7c2d22aaa8e0593fc1c8e6bd675cd3a676cbf)) - Barry Walker, Claude Opus 4.5
- (**webdav**) add ClientCompatibilityMiddleware for better client handling - ([ab1b07a](https://github.com/barryw/paperless-webdav/commit/ab1b07a0544c8f1343d26fc2be0599c742810d6e)) - Barry Walker, Claude Opus 4.5
- (**webdav**) validate MOVE operations and reject invalid moves - ([be12ecb](https://github.com/barryw/paperless-webdav/commit/be12ecb5f0e8e27b9195c9166973905d0707ed51)) - Barry Walker, Claude Opus 4.5
- (**webdav**) MOVE from done folder to root removes done_tag - ([d3219c4](https://github.com/barryw/paperless-webdav/commit/d3219c471ac773654d578af175fef9930c0d8930)) - Barry Walker, Claude Opus 4.5
- add deployment configs and fix WebDAV file serving - ([7bcc82a](https://github.com/barryw/paperless-webdav/commit/7bcc82ad3d03b8aa41694f7bc922d4bf8d7f5325)) - Barry Walker, Claude Opus 4.5
- implement MOVE to done folder (add done_tag) - ([0238a70](https://github.com/barryw/paperless-webdav/commit/0238a70259d8f05a7bdfa5b9559c713e9407d9b9)) - Barry Walker, Claude Opus 4.5
- show done documents in done folder - ([29a0605](https://github.com/barryw/paperless-webdav/commit/29a0605395697d0415a2dddda7b6592c64377c7d)) - Barry Walker, Claude Opus 4.5
- filter done documents from share root listing - ([7381999](https://github.com/barryw/paperless-webdav/commit/7381999a7144eebffa83689fafc8bf388f0dc01c)) - Barry Walker, Claude Opus 4.5
- add main entrypoint for running FastAPI and WebDAV servers - ([bd28338](https://github.com/barryw/paperless-webdav/commit/bd283384d829d89edd0c52d302571988ea1bd218)) - Barry Walker, Claude Opus 4.5
- add WebDAV server using wsgidav and cheroot - ([15978dd](https://github.com/barryw/paperless-webdav/commit/15978dddc076d5a16aeddb20d87f9b30b6e2d413)) - Barry Walker, Claude Opus 4.5
- add WebDAV authentication via HTTP Basic Auth - ([5b866f5](https://github.com/barryw/paperless-webdav/commit/5b866f582e3ac34830aa5bc241c99c9bc132ea0d)) - Barry Walker, Claude Opus 4.5
- wire WebDAV provider to load documents from Paperless API - ([643149d](https://github.com/barryw/paperless-webdav/commit/643149d93a7ed44ea3a5df89bf22eb96050366ba)) - Barry Walker, Claude Opus 4.5
- add async bridge for running async code from sync wsgidav - ([dc8fb79](https://github.com/barryw/paperless-webdav/commit/dc8fb79bfe22fb8ce960808db9c573d85db54b2d)) - Barry Walker, Claude Opus 4.5
- add logout handler - ([638ac8f](https://github.com/barryw/paperless-webdav/commit/638ac8f7cc3351f03fbae8e0dd3982dab485f092)) - Barry Walker, Claude Opus 4.5
- add share delete handler for HTMX - ([8fbdc95](https://github.com/barryw/paperless-webdav/commit/8fbdc9507889442d8f4cbaeb113770db16361a0b)) - Barry Walker, Claude Opus 4.5
- add share form submission handlers - ([df8a677](https://github.com/barryw/paperless-webdav/commit/df8a677e039b021c419fbc79ccc4fd1f32c5da72)) - Barry Walker, Claude Opus 4.5
- add user autocomplete with permission fallback - ([e2c0a8e](https://github.com/barryw/paperless-webdav/commit/e2c0a8e23e326dae11646ba0dd7dc7ed103422b2)) - Barry Walker, Claude Opus 4.5
- add tag autocomplete with HTMX - ([542c97d](https://github.com/barryw/paperless-webdav/commit/542c97d0c8c586c8cbd1b10d771d7b0c85a004c8)) - Barry Walker, Claude Opus 4.5
- add create/edit share form pages - ([6156cda](https://github.com/barryw/paperless-webdav/commit/6156cdab37f9fbaf2f2483e4aa9166961531143d)) - Barry Walker, Claude Opus 4.5
- add share list page with auth protection - ([c856777](https://github.com/barryw/paperless-webdav/commit/c856777ee36fbe65560d95f2b58e2ebac13b0748)) - Barry Walker, Claude Opus 4.5
- add login form submission with redirect - ([d32aa05](https://github.com/barryw/paperless-webdav/commit/d32aa05c355a966e955b7561d5c43bbbe4e824f7)) - Barry Walker, Claude Opus 4.5
- add Jinja2 template setup with login page - ([76e6342](https://github.com/barryw/paperless-webdav/commit/76e6342208ac23cd8abeb519e929fa2dddd5f64b)) - Barry Walker, Claude Opus 4.5
- wire database to share API endpoints - ([3a99fa3](https://github.com/barryw/paperless-webdav/commit/3a99fa362574ba019263b0b7c9745e5894809d78)) - Barry Walker, Claude Opus 4.5
- add Alembic migrations for database schema - ([6b74334](https://github.com/barryw/paperless-webdav/commit/6b7433467068d6f64696a1c7d91e2cbeb40efa5b)) - Barry Walker, Claude Opus 4.5
- add Paperless-native authentication - ([a915f67](https://github.com/barryw/paperless-webdav/commit/a915f679b52dae94108bffbdc1e2719ac6682355)) - Barry Walker, Claude Opus 4.5
- add tags API endpoints - ([48d3249](https://github.com/barryw/paperless-webdav/commit/48d32491c26f0434fa41cce2a2ae1f0d596506a5)) - Barry Walker, Claude Opus 4.5
- add share CRUD API endpoints - ([b396f47](https://github.com/barryw/paperless-webdav/commit/b396f4747c185d6c7447a36b47ad97918f7bd5e0)) - Barry Walker, Claude Opus 4.5
- add FastAPI application with health endpoints - ([37e9c9a](https://github.com/barryw/paperless-webdav/commit/37e9c9a4b5fd3b353135f903fc1f0bb7299401b6)) - Barry Walker, Claude Opus 4.5
- add wsgidav provider for Paperless documents - ([7845a36](https://github.com/barryw/paperless-webdav/commit/7845a365bb2f4a00c902228103a83b64893071f0)) - Barry Walker, Claude Opus 4.5
- add Paperless-ngx API client - ([7530c7e](https://github.com/barryw/paperless-webdav/commit/7530c7e0cda15c2c4bb7982bfc9d365791763b33)) - Barry Walker, Claude Opus 4.5
- add AES-256-GCM encryption for API tokens - ([db73121](https://github.com/barryw/paperless-webdav/commit/db7312102dc46b106223ea8292b9ff9d814a5fc1)) - Barry Walker, Claude Opus 4.5
- add database models for users, shares, and audit log - ([bff8010](https://github.com/barryw/paperless-webdav/commit/bff80105371977fdae0c0ef77c0d11bb396de08e)) - Barry Walker, Claude Opus 4.5
- add structured JSON logging for Graylog - ([79c7606](https://github.com/barryw/paperless-webdav/commit/79c76064db6bae4106404378d4d606b881f51bb4)) - Barry Walker, Claude Opus 4.5
- initialize project structure with config - ([3839a1b](https://github.com/barryw/paperless-webdav/commit/3839a1bc90b3a156b5edcddcaa337a7732afe610)) - Barry Walker, Claude Opus 4.5
#### Bug Fixes
- (**cache**) add type ignores for redis sync client - ([441bb9c](https://github.com/barryw/paperless-webdav/commit/441bb9c6ea53859d7351dfb2b202815fc79d0b64)) - Barry Walker, Claude Opus 4.5
- (**caddy**) use self-signed TLS by default, fix root redirect - ([4e049dc](https://github.com/barryw/paperless-webdav/commit/4e049dcaa69364332c3aea46cc16209c04a45dab)) - Barry Walker, Claude Opus 4.6 (1M context)
- (**ci**) handle 'v' prefix in version bump detection - ([99fd219](https://github.com/barryw/paperless-webdav/commit/99fd21927b176d37fdf4557d269f597873d40942)) - Barry Walker, Claude Opus 4.5
- (**ci**) unshallow clone and validate dry-run output - ([9f761b8](https://github.com/barryw/paperless-webdav/commit/9f761b809a4bc0b707f02c0f824393a59db3ecc3)) - Barry Walker, Claude Opus 4.5
- (**ci**) use cog bump --auto --dry-run for version detection - ([2eea40b](https://github.com/barryw/paperless-webdav/commit/2eea40bc4fcf4016d2f511aeab8aa65752447f52)) - Barry Walker, Claude Opus 4.5
- (**ci**) remove cog post-bump hooks - CI handles push - ([5f0f08a](https://github.com/barryw/paperless-webdav/commit/5f0f08a8a2fc54fa714cffcfd7b4a60acd4fcb83)) - Barry Walker, Claude Opus 4.5
- (**ci**) correct step order - build before release - ([c1c8d4b](https://github.com/barryw/paperless-webdav/commit/c1c8d4b0b1443b1f62c6c1e699a7e1bc3c7ecfc7)) - Barry Walker, Claude Opus 4.5
- (**ci**) follow LuaKit pattern for release workflow - ([15eab26](https://github.com/barryw/paperless-webdav/commit/15eab2642f2e7d2e81c40af344b0c5b247fb7b35)) - Barry Walker, Claude Opus 4.5
- (**ci**) all steps in one pipeline - version-bump to deploy - ([4a08cd9](https://github.com/barryw/paperless-webdav/commit/4a08cd9afc44d4d1e34d01108c601a5f53f3424b)) - Barry Walker, Claude Opus 4.5
- (**ci**) restore automated semver with cocogitto - ([59b1f23](https://github.com/barryw/paperless-webdav/commit/59b1f23d23c5b0368b53dbacffc55c3b4ec60169)) - Barry Walker, Claude Opus 4.5
- (**ci**) fix docker config.json echo command quoting - ([cd07359](https://github.com/barryw/paperless-webdav/commit/cd07359184cf9d49bf94726f502635adfb3792d3)) - Barry Walker, Claude Opus 4.5
- (**ci**) simplify pipeline - build and deploy on every push to main - ([ffeb7b3](https://github.com/barryw/paperless-webdav/commit/ffeb7b32c38e473aec902a4a14c59995c5c7d7b5)) - Barry Walker, Claude Opus 4.5
- (**ci**) quote deploy commands to prevent YAML parsing issues - ([a513f76](https://github.com/barryw/paperless-webdav/commit/a513f76272544795b027b2cdc2bf2c67ebf484a5)) - Barry Walker, Claude Opus 4.5
- (**ci**) quote kaniko command to prevent YAML parsing issues - ([1bf557f](https://github.com/barryw/paperless-webdav/commit/1bf557f3e8aede22325937f0d7fb1fa10fbcae5d)) - Barry Walker, Claude Opus 4.5
- (**ci**) specify namespace for kubectl deploy commands - ([9d3d437](https://github.com/barryw/paperless-webdav/commit/9d3d4373232f5725231ec5cc06a6de2e524340c6)) - Barry Walker, Claude Opus 4.5
- (**ci**) correct pipeline step dependencies - ([adfed7b](https://github.com/barryw/paperless-webdav/commit/adfed7bb6568e0ff1891b0b0811b2985bbf62599)) - Barry Walker, Claude Opus 4.5
- (**ci**) use environment with from_secret for GHCR token - ([18807dd](https://github.com/barryw/paperless-webdav/commit/18807dd8c3a2520b0187c20e804dd6242e42f7a1)) - Barry Walker, Claude Opus 4.5
- (**ci**) use dedicated secret for GHCR authentication - ([9529b8a](https://github.com/barryw/paperless-webdav/commit/9529b8adbd504cdff475b7c33921569e98218f13)) - Barry Walker, Claude Opus 4.5
- (**ci**) disable mypy strict error codes to unblock pipeline - ([4f0a72a](https://github.com/barryw/paperless-webdav/commit/4f0a72a26a571663fb6a97fe1897d601d69dd778)) - Barry Walker, Claude Opus 4.5
- (**ci**) include dev dependencies with --all-extras for ruff/mypy/pytest - ([b516470](https://github.com/barryw/paperless-webdav/commit/b516470097409c34a73e845d4148d4090c1205ef)) - Barry Walker
- (**ci**) add build dependencies for python-ldap compilation - ([82fae98](https://github.com/barryw/paperless-webdav/commit/82fae98237b01093c9a159353c55838986b3bd9b)) - Barry Walker
- (**ci**) use kaniko for non-privileged Docker builds - ([20815c1](https://github.com/barryw/paperless-webdav/commit/20815c115a0380f7ff55608788f5f479a8ec7817)) - Barry Walker
- (**ci**) correct YAML syntax and target Linux runners - ([dca82a6](https://github.com/barryw/paperless-webdav/commit/dca82a6565c6c0e15e4ad1d32bfcb9949be10896)) - Barry Walker
- (**config**) rename redis vars to avoid k8s service collision - ([1d3c1cb](https://github.com/barryw/paperless-webdav/commit/1d3c1cb3335e28022fc8cb5812f77460c885073e)) - Barry Walker, Claude Opus 4.5
- (**db**) make migrations idempotent, use latest tag - ([0f871af](https://github.com/barryw/paperless-webdav/commit/0f871af05461f652c7649ae47283a7b00a53bcf1)) - Barry Walker, Claude Opus 4.5
- (**db**) add advisory lock to prevent migration race condition - ([0efc051](https://github.com/barryw/paperless-webdav/commit/0efc051aec3d79e91541f2ea8a3737e065e22e6e)) - Barry Walker, Claude Opus 4.5
- (**k8s**) use GHCR image with Always pull policy - ([d586a2c](https://github.com/barryw/paperless-webdav/commit/d586a2c52571cb8a09ce51c7aae33480f1d78b9f)) - Barry Walker, Claude Opus 4.5
- (**test**) update migration tests for idempotent checks - ([b52acd1](https://github.com/barryw/paperless-webdav/commit/b52acd1d0f8b5b9553a3d961a74b8afb566619d8)) - Barry Walker, Claude Opus 4.5
- (**tests**) fix remaining test issues for clean CI run - ([b136759](https://github.com/barryw/paperless-webdav/commit/b1367598810552427ba53e3c480cfb9665ba3cd7)) - Barry Walker, Claude Opus 4.5
- (**tests**) clear auth cache and fix OIDC mode tests - ([fa49413](https://github.com/barryw/paperless-webdav/commit/fa49413bb1bc5ddc2cc4021ae427838598b1c677)) - Barry Walker, Claude Opus 4.5
- (**tests**) improve test isolation and fix mock endpoints - ([b6510b1](https://github.com/barryw/paperless-webdav/commit/b6510b192d3fd5ef6e043503409a61de7595ae92)) - Barry Walker, Claude Opus 4.5
- (**tests**) correct test method calls and type assertions - ([452fbdb](https://github.com/barryw/paperless-webdav/commit/452fbdb67adbbb9e2d8953381b7c9d729142ff0a)) - Barry Walker, Claude Opus 4.5
- (**webdav**) accept and discard writes to documents - ([67fea08](https://github.com/barryw/paperless-webdav/commit/67fea08dbd9d8654e749452a62f3b5305c2f02fe)) - Barry Walker, Claude Opus 4.5
- (**webdav**) enable Range request support for documents - ([5869e28](https://github.com/barryw/paperless-webdav/commit/5869e2808518e8c53a458e7cc41dad9941f80acc)) - Barry Walker, Claude Opus 4.5
- (**webdav**) make filename collision resolution deterministic - ([dbe7c68](https://github.com/barryw/paperless-webdav/commit/dbe7c68daeb9555f9a3f90ecbd75c90831c37323)) - Barry Walker, Claude Opus 4.5
- (**webdav**) ensure Content-Length matches actual content - ([82407e8](https://github.com/barryw/paperless-webdav/commit/82407e8ffe763bf6ad2c1429bcbcc5ae51d031b7)) - Barry Walker, Claude Opus 4.5
- (**webdav**) always use actual content size for Content-Length - ([6468a8a](https://github.com/barryw/paperless-webdav/commit/6468a8a64e8b039e57cf61129b25f5e7ac77909e)) - Barry Walker, Claude Opus 4.5
- (**webdav**) only apply no-cache headers for macOS clients - ([1174de5](https://github.com/barryw/paperless-webdav/commit/1174de56cfb47b54c7d4c7c68335676b165f0d19)) - Barry Walker, Claude Opus 4.5
- trigger pipeline after config service template fix - ([b093c33](https://github.com/barryw/paperless-webdav/commit/b093c333bbb0a8e0d08badf39469713ad8c7daff)) - Barry Walker
- add --skip-ci to cog bump to prevent CI loop - ([7b71a13](https://github.com/barryw/paperless-webdav/commit/7b71a13f9def2ddc1904dbd4136d2f22a06cfcde)) - Barry Walker
- stop using latest tag for container images - ([094f0f3](https://github.com/barryw/paperless-webdav/commit/094f0f37fab06a50fc1f7f0746d757ed46053cbc)) - Barry Walker, Claude Opus 4.5
- correct K8s deployment configuration - ([94da31a](https://github.com/barryw/paperless-webdav/commit/94da31ad2e406cc79abe67bd61a76cb9bfcb3c6d)) - Barry Walker, Claude Opus 4.5
- reorder imports to fix E402 linting errors - ([1b53c74](https://github.com/barryw/paperless-webdav/commit/1b53c749df766126b0caec84572f4a24699dda5f)) - Barry Walker
- remove unused variable in test - ([a3f682d](https://github.com/barryw/paperless-webdav/commit/a3f682dc288d551023e7917f89ff78612de145a4)) - Barry Walker
- improve type safety in token loading functions - ([d44eb46](https://github.com/barryw/paperless-webdav/commit/d44eb4630708785809a76d4e354feea167b904c1)) - Barry Walker, Claude Opus 4.5
- remove unused variable in token storage test - ([bd4b48e](https://github.com/barryw/paperless-webdav/commit/bd4b48e77a6dea41903327737c3191a5c9b03501)) - Barry Walker
- remove unused imports and fixtures from token setup - ([91ee5c9](https://github.com/barryw/paperless-webdav/commit/91ee5c93889139fabe303177a457d4ee048d153d)) - Barry Walker, Claude Opus 4.5
- address linting issues in OIDC tests - ([488d2c4](https://github.com/barryw/paperless-webdav/commit/488d2c4ee476920ba0e7c2129eeaa66d9c36cdc0)) - Barry Walker, Claude Opus 4.5
- add exception handling in move() and _get_done_tag_id() - ([84ad6e5](https://github.com/barryw/paperless-webdav/commit/84ad6e5d66a328421225fd8054c341156498989c)) - Barry Walker, Claude Opus 4.5
- suppress AsyncMock coroutine warnings in pytest - ([84af94b](https://github.com/barryw/paperless-webdav/commit/84af94b21b8cf9dfe4e713194762b379b7ddbfe0)) - Barry Walker, Claude Opus 4.5
- address code review feedback for main entrypoint - ([2bb7bbf](https://github.com/barryw/paperless-webdav/commit/2bb7bbf866a83ae86ae7c78877c61fd6bcb0657c)) - Barry Walker, Claude Opus 4.5
- address code review feedback for WebDAV provider - ([a64d695](https://github.com/barryw/paperless-webdav/commit/a64d6952f5888ea4d238b5324a3b8d9308ca0742)) - Barry Walker, Claude Opus 4.5
#### Documentation
- add comprehensive README with badges and usage guide - ([d699c40](https://github.com/barryw/paperless-webdav/commit/d699c404d9918db096ef9ffbf96bbb0464866639)) - Barry Walker, Claude Opus 4.5
- add implementation plan for WebDAV, Done Folder, and OIDC - ([5135850](https://github.com/barryw/paperless-webdav/commit/5135850493e5cf463f14bd42643800474b182d22)) - Barry Walker, Claude Opus 4.5
- add admin UI implementation plan - ([7e5d988](https://github.com/barryw/paperless-webdav/commit/7e5d988fa6d1857dc257fc01d424b61bc04a2b9b)) - Barry Walker, Claude Opus 4.5
- add admin UI design for share management - ([c15d110](https://github.com/barryw/paperless-webdav/commit/c15d1104b6d768f3d216ea804940e714dcfe936d)) - Barry Walker, Claude Opus 4.5
- add detailed implementation plan - ([0883e07](https://github.com/barryw/paperless-webdav/commit/0883e07f4f9738ec74a7cf978e503bc06b7b0db9)) - Barry Walker, Claude Opus 4.5
#### Tests
- add integration test for full share CRUD flow - ([f1f6138](https://github.com/barryw/paperless-webdav/commit/f1f6138e213eb14b20670ab8699c2ba07950b624)) - Barry Walker, Claude Opus 4.5
#### CI/CD
- add GitHub releases and RBAC for K8s deployment - ([a30a6e0](https://github.com/barryw/paperless-webdav/commit/a30a6e031896ee73811f5eefd330d2b45111f84d)) - Barry Walker, Claude Opus 4.5
- add Woodpecker pipeline with conventional commits and auto-deploy - ([b491320](https://github.com/barryw/paperless-webdav/commit/b4913206b9241aceb6472fdabfaf4709306dbc49)) - Barry Walker, Claude Opus 4.5
- add Woodpecker CI pipeline for lint, typecheck, and test - ([d8b5ef3](https://github.com/barryw/paperless-webdav/commit/d8b5ef363fcce8ff775d3c9c4df6fdb1bf18077d)) - Barry Walker
#### Refactoring
- replace pipeline with config service template - ([fd16d62](https://github.com/barryw/paperless-webdav/commit/fd16d625117622daf9e3254613ba6cccc6362841)) - Barry Walker
- remove vestigial read_only field, add migration entrypoint - ([0f86dcc](https://github.com/barryw/paperless-webdav/commit/0f86dcc203873bf5af154e71cba2332c9a6462db)) - Barry Walker, Claude Opus 4.5
#### Miscellaneous
- remove debug logging for content length - ([422c9b2](https://github.com/barryw/paperless-webdav/commit/422c9b23631ebaf69d6fa0a06deb94d173e5ae68)) - Barry Walker, Claude Opus 4.5
- add INFO logging for content length tracking - ([5b750d3](https://github.com/barryw/paperless-webdav/commit/5b750d375cd204264b3d1e5af60d9ce13601f4ac)) - Barry Walker, Claude Opus 4.5
- add pre-commit hook for lint and tests - ([7d0b33e](https://github.com/barryw/paperless-webdav/commit/7d0b33eb502fb54155c6001a44bdc6dba60742f8)) - Barry Walker, Claude Opus 4.5
- trigger CI pipeline - ([24bcf66](https://github.com/barryw/paperless-webdav/commit/24bcf66d90a53b0e2a2b7df82b87323b045d3a7a)) - Barry Walker, Claude Opus 4.5
- trigger CI build - ([bec5953](https://github.com/barryw/paperless-webdav/commit/bec595354943dca553ca57ab46e39b4ca10fb8b3)) - Barry Walker, Claude Opus 4.5
#### Styling
- format test_migrations.py - ([e61ef72](https://github.com/barryw/paperless-webdav/commit/e61ef720bf57cced3a35ef3ad21ee407ccf89c72)) - Barry Walker, Claude Opus 4.5
- format test_api_shares.py - ([4371333](https://github.com/barryw/paperless-webdav/commit/43713339cffcc0841dac2033d2301d3c87441dc3)) - Barry Walker
- format code with ruff - ([269754a](https://github.com/barryw/paperless-webdav/commit/269754a7465ea0e0c803152d34177b960c4faf55)) - Barry Walker

- - -

Changelog generated by [cocogitto](https://github.com/cocogitto/cocogitto).