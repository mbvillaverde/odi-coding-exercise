# ODI Exercise: Multi-Tenant Insurance Claims Platform with Async Processing

## Architecture Overview
```
├── claims
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── filters.py
│   ├── management
│   │   └── commands
│   │       ├── __init__.py
│   │       └── populate_data.py
│   ├── migrations
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   ├── models.py
│   ├── permissions.py
│   ├── serializers.py
│   ├── tasks.py
│   ├── tests
│   │   ├── __init__.py
│   │   ├── test_api.py
│   │   ├── test_models.py
│   │   ├── test_permissions.py
│   │   └── test_tasks.py
│   ├── validators.py
│   └── views.py
├── compose.yaml
├── initialize_project.sh
├── manage.py
├── project
│   ├── __init__.py
│   ├── asgi.py
│   ├── celery.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── pyproject.toml
├── README.md
├── tenancy
│   ├── __init__.py
│   ├── apps.py
│   ├── middleware.py
│   ├── migrations
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   ├── models.py
│   └── utils.py
└── uv.lock
```

## How to run the project

1. Ensure that you have the following tools in your machine.
* [Docker](https://docs.docker.com/engine/install/)
* [Docker Compose](https://docs.docker.com/compose/install/)
* [UV](https://docs.astral.sh/uv/getting-started/installation/)

2. Open the terminal and run the following:
```bash
bash initialize_project.sh
```

3. Step 2 will run the following process:
* Spins up Postgres and Redis containers
* Install project dependencies
* Migrate tables and populate test data to tables
* Run coverage and unit tests
* Show coverage report
* Run celery workers in the background
* Run Django Server

4. Optionally, you can follow the commands indicated in `initialize_project.sh` to playaround the project.

## Questions

### Multi-Tenancy Strategy
- How do you isolate tenants? **Ans:** Created an abstract model `TenantModel` that holds the organization column.
- Where is tenant context set and checked? **Ans:** Tenant is set in `middleware.py` which enables setting and resetting of tenant for each request.
- How do you prevent cross-tenant data leaks? **Ans:** By ensuring that each table will inherit the `TenantModel` so that the model can be aware on what organization it's part of.

### Database Schema
- Models and relationships
- Why you added specific fields beyond core? **Ans:** I haven't add any specific fields besides the ones mentioned.
- Index strategy: which fields indexed, why? **Ans:** I haven't add any new index.
- Any denormalized fields for performance? **Ans:** I haven't applied any denormalization.

### Permission Model
- How are permissions enforced? (queryset level, view level) **Ans:** Models that inherit `TenantModel` are using custom manager `TenantManager` to encapsulate the queryset results to own organization. User role permissions are handed using custom permission `CanManageClaim`.
- Where do permission checks happen? **Ans:** It is handled in `ViewSet` level, specified in `permission_classes` class attribute.
- Can permissions be bypassed? (Should be no) **Ans:** No, it cannot be bypassed
- How do you test permission boundaries? **Ans:** For unit tests, ensure that you assign a role in `User` object to successfully check permissions in views.

### Async Processing with Celery
- Which tasks exist and what do they do? **Ans:** The tasks are `process_patient_admission`, `process_patient_discharge` and `process_treatment_initiated`. They update claim `status` in the background to `UNDER_REVIEW` or `APPROVED`.
- Idempotency strategy: how do you prevent duplicate processing? **Ans:** By using `select_for_update` process as this ensures data integrity of the selected set of data.
- Retry logic: exponential backoff? Max retries? How to recover? **Ans:** Exponential backoff is enabled using `retry_backoff` and max retries are set to `3`.
- Transaction safety: atomic operations? **Ans:** Atomic operations are enabled by adding it into the context of `transaction.atomic`
- How do you know if a task failed? **Ans:** Tasks are saved in redis mentioned in `CELERY_RESULT_BACKEND` which contains `status` that can result as `FAILURE` or `SUCCESS`.

### Performance Optimization
- Query optimization: prefetch_related, select_related strategy **Ans:** Applied the `prefetch_related` in the views.
- Pagination approach (offset vs. cursor) **Ans:** I used the `LimitOffsetPagination` class as default pagination for the views.
- Indexes and why you chose them **Ans:** I haven't add any new index
- Any benchmarks/query analysis **Ans:** I haven't add any benchmark to be viewed on but I added test `test_list_endpoint_performance` to apply basic performance assertions.

### Testing Strategy
- Unit vs. integration tests ✅
- Critical paths tested thoroughly ✅
- Edge cases covered ✅
- Security testing: permission bypass attempts tested ✅
- Async testing: idempotency verified ✅

### Trade-offs Made
- What did you prioritize? **Ans:** I prioritied unit testing to further check for edge case scenarios.
- Known limitations? **Ans:** Since some of the scenarios can be mocked or modified at setup, this might not be align on how actual users use the application.

### What You'd Do With More Time
- Performance optimizations not implemented? **Ans:** More thorough validations specially on how codes are being checked. More granular approach on creating serializers (e.g. filtering choices based on user roles). Code refactoring specially on the unit test.
- Additional features? **Ans:** Applying celery beat workers to check overdue or expired submitted claims.
- Testing coverage gaps? **Ans:** There might be some scenarios that I haven't tackled for specific user behaviors.