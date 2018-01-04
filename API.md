
API PERMISSIONS
---------------

The API simply does not allow events to be modified after they are created - events are write-only.

Site admins are intentionally hardcoded, and have almost zero restrictions.

Service admins are granted almost unlimited access to modify their service metadata, users for the service, and api-keys

Updaters are only allowed to submit events to a single service per API key.

Everybody is allowed to view almost all data about services, except for permitted users.

+-------------------------------------------------+---------------------+---------------------+----------+-----------------+-----------+
|                                                 |                                  Access permissions                                |
+-------------------------------------------------+---------------------+---------------------+----------+-----------------+-----------+
| Endpoint                                        |     Site admins     |    Service admins   | Updaters |      Users      | Everybody |
+-------------------------------------------------+---------------------+---------------------+----------+-----------------+-----------+
| /status                                         |                     |                     |          |                 |  GET      |
| /services                                       |     POST            |                     |          |                 |  GET      |
| /services/{service_slug}                        |          PUT        |          PUT        |          |                 |  GET      |
| /services/{service_slug}/status                 |                     |                     |          |                 |  GET      |
| /services/{service_slug}/events                 |     POST            |     POST            |     POST |                 |  GET      |
| /services/{service_slug}/events/{event_id}      |                     |                     |          |                 |  GET      |
| /services/{service_slug}/permissions            | GET POST            | GET POST            |          | GET             |           |
| /services/{service_slug}/permissions/{username} | GET      PUT DELETE | GET      PUT DELETE |          | GET             |           |
|                                                 |                     |                     |          |                 |           |
| /api-keys                                       |     POST            |     POST            |          |     POST        |           |
+-------------------------------------------------+---------------------+---------------------+----------+-----------------+-----------+



ENDPOINTS
---------

Pagination is recommended for some endpoints but not all (use your best judgment). Among other
things, the '...' shorthand implies pagination information included where reasonable.

/status

  GET - A dictionary of all services and their current status.

        If service is up, the response should include a list containing the last event with an "Up"
        status.

        If a service is down or limited, its dictionary should include a list of events since the
        last time it was up (but not including the last time it was up).

        Example:
        {
            ...
            "results": {
                "Jira": {
                    "url": "/services/jira",
                    "status": "Up",
                },
                "Confluence": {
                    "url": "/services/confluence",
                    "status": "Down",
                    "events": [
                        {
                            "url": "/services/confluence/events/00001111-2222-3333-4444-555566667777",
                            "status": "Down",
                            "when": <timestamp>,
                            "informational": true,
                            "description": ...,
                            "extra": {}
                        }, {
                            "url": "/services/confluence/events/00001111-2222-3333-4444-555566667778",
                            "status": "Down",
                            "when": <timestamp>,
                            "informational": false,
                            "description": ...,
                            "extra": {}
                        }
                    ]
                }
                ...
            }
        }

/services

  GET - List all services

        The `slug` field is read-only and is set automatically from the service name.

        Example:
        {
            ...,
            "results": [
                {
                    "url": "/services/jira",
                    "name": "Jira",
                    "description": "Track issues, submit requests,
                    "slug": "jira"
                },
                ...
            ]
        }

  POST - Create a new service

         Only site admins are allowed to create services

         Example:
         {
             "name": "Jira",
             "description": "Track issues, submit service requests"
         }

/services/{service_slug}

  GET - Get the metadata for a service

        Example:
        {
            "url": "/services/jira",
            "name": "Jira",
            "description": "Track issues, submit service requests",
            "slug": jira
        }

  PUT - Update the metadata of a service

        Only site admins and service admins are allowed to update service metadata

        Example:
        {
            "name": "Jira",
            "description": "Track issues, submit service requests"
        }

/services/{service_slug}/status

  GET - Get the status for a specific service

        If service is up, the response should include a list containing the last event with an "Up"
        status.

        If service is down or limited, the response should include a list of events since the last
        time it was up (but not including the last time it was up).

        Example:
        {
            "url": "/services/jira/status",
            "status": "Up",
            "events": [
                {
                    "url": "/services/jira/events/88887777-6666-5555-4444-333322221111",
                    "status": "Up",
                    "when": <timestamp>,
                    "informational": true,
                    "description": ...,
                    "extra": {}
                }
            ]
        }

        Example:
        {
            "url": "/services/confluence/status",
            "status": "Down",
            "events": [
                {
                    "url": "/services/confluence/events/00001111-2222-3333-4444-555566667777",
                    "status": "Down",
                    "when": <timestamp>,
                    "informational": true,
                    "description": ...,
                    "extra": {}
                }, {
                    "url": "/services/confluence/events/00001111-2222-3333-4444-555566667778",
                    "status": "Down",
                    "when": <timestamp>,
                    "informational": false,
                    "description": ...,
                    "extra": {}
                }
            ]
        }

/services/{service_slug}/events

  GET - List of all events for a service

        Example:
        {
            ...,
            "results": [
                {
                    "url": "/services/confluence/events/00001111-2222-3333-4444-555566667777",
                    "status": "Up",
                    "description": "All systems normal",
                    "informational": false,
                    "extra": {}
                },
                ...
            ]
        }

  POST - Create a new event for a service

         Only site admins, service admins, and service updaters are allowed to submit events for a
         service, and the appropriate security controls should apply depending on the user
         permission.

         Example:
         {
             "status": "Up",
             "description": "All systems normal",
             "informational": true,
             "extra": {
                 "from": "Sensu",
                 "node": "sensu-1-001.live.sre.las1.mz-inc.com"
             }
         }

/services/{service_slug}/events/{event_id}

  GET - Get data from a specific event

        Example:
        {
            "url": "/services/confluence/events/00001111-2222-3333-4444-555566667777",
            "status": "Up",
            "description": "All systems normal",
            "informational": false,
            "extra": {}
        }

/services/{service_slug}/permissions

  GET - List of users who have permissions for a service

        Only admins may make requests to this endpoint.

        Example:
        {
            ...,
            "results": [
                {
                    "username": <username>,
                    "permission": <service-admin|updater>
                },
                ...
            ]
        }

  POST - Grant a user permission for a service

         Only admins may make requests to this endpoint.

         Site admins may create permissions for anybody.

         Service admins may only create permissions for their services.

         Example:
         {
             "username": <username>,
             "permission": <service-admin>
         }

/services/{service_slug}/permissions/{username}

  GET - Get a user's permissions for a service

        This endpoint can return `null` if the user does not have permission for the service.

        Example:
        {
            "permission": <service-admin|updater>
        }

        Example:
        null

  PUT - Update a user's permissions for a service

        Example:
        {
            "permission": <service-admin|updater>
        }

  DELETE - Remove a user's permissions for a service

/api-keys

  POST - Create an API key for a user

         SECURITY NOTE: This endpoint cannot accept authentication from self-issued API keys/JWTs.

         This endpoint returns an API key, which is really just a JWT issued by this server.

         Site admins can create API keys that do not expire for anybody.

         Service admins can create API keys that do not expire for services that they own.

         Non-admin users can create API keys that have non-null expirations.

         Site admins should be able to create API keys for anybody for any service.

         Service admins can create API keys for other users for a service they administrate. This
         can be useful for creating API keys for updaters and other bots.

         Users can create API keys to authenticate as themselves, and all API keys will have the
         same restrictions that the user has in the system.

         The API key data will only be returned once. This is a write-only, read-once endpoint.
         If the API key is forgotten or otherwise inaccessible, another API key must be generated
         (and the original API key should be removed).

         Example:
         {
             "id": <UUID>,
             "username": <username>
             "key": ...
         }
