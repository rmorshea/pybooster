# Tutorial

This tutorial will guide you through the process of creating a "To-Do" application using
PyBooster to facilitate access to various services and resources. The application will
include a basic UI built using [HTMX](https://htmx.org/) and be able to create, read,
update, and delete tasks that support file attachments.

```mermaid
architecture-beta
    service client(internet)[Client]
    service db(database)[Database]
    service storage(disk)[Storage]
    service server(server)[Server]
    junction serverRight1
    junction serverRight2

    client:R --> L:server
    server:R -- L:serverRight1
    serverRight1:R -- L:serverRight2
    serverRight1:B --> T:db
    serverRight2:B --> T:storage
```
