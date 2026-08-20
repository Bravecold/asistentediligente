# AsistenteDiligente

MVP de un marketplace colombiano que conecta a personas que necesitan completar diligencias digitales con gestores que aportan asistencia y conocimiento. La plataforma organiza, asigna y deja trazabilidad; **no representa legalmente al usuario, no garantiza resultados ante terceros y nunca solicita contraseñas, códigos OTP, claves bancarias ni datos completos de tarjetas**.

## Qué incluye

- Portal estático accesible para explorar procedimientos OPS, crear solicitudes y visualizar la operación.
- API REST con catálogo de entidades/trámites, solicitudes, asignación, transiciones y auditoría.
- Roles iniciales: `customer`, `beneficiary`, `manager`, `supervisor` y `admin`.
- PostgreSQL con modelo relacional y eventos de auditoría encadenados por hash.
- Consentimiento versionado y separado para datos personales y datos sensibles de salud.
- Infraestructura Bicep: Storage Static Website, App Service Linux y PostgreSQL Flexible Server.
- Despliegue por GitHub Actions usando federación OIDC, sin secretos permanentes de Azure.

## Arquitectura rápida

```text
Navegador -> Azure Storage Static Website
     |                 |
     +---- HTTPS ------+----> App Service (FastAPI) ---> PostgreSQL
                                |                             |
                          RBAC + validación              auditoría hash-chain
```

Detalles y decisiones: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Modelo: [docs/DATA_MODEL.md](docs/DATA_MODEL.md). Backlog: [docs/BACKLOG.md](docs/BACKLOG.md).

## Ejecutar localmente

Requisitos: Python 3.12+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

En otra terminal:

```bash
cd frontend
cp config.example.js config.js
python -m http.server 5173
```

Abra `http://localhost:5173`. La API usa SQLite local si `DATABASE_URL` no está definida. En modo desarrollo, el frontend envía `X-Demo-Role`; esto queda deshabilitado cuando `APP_ENV=production`.

## Pruebas

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## Desplegar en Azure

1. Cree una identidad federada de GitHub para Azure y configure los secretos `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` y `AZURE_SUBSCRIPTION_ID` en el repositorio.
2. Cree el secreto de entorno `POSTGRES_ADMIN_PASSWORD` en el environment `production`.
3. Ejecute el workflow **Deploy Azure** manualmente. También puede usar:

```bash
./scripts/deploy.sh <subscription-id> <resource-group> <location>
```

El despliegue crea recursos con nombres únicos, publica la API, inicializa las tablas al arrancar y carga el frontend configurado con la URL real de la API. Antes de producción, sustituya la autenticación demo por Microsoft Entra External ID y restrinja CORS al dominio final.

## Alcance jurídico y de seguridad

Los textos en [docs/PRIVACY_NOTICE.md](docs/PRIVACY_NOTICE.md) y [docs/MARKETPLACE_TERMS.md](docs/MARKETPLACE_TERMS.md) son borradores operativos basados en la Ley 1581 de 2012 y el Decreto 1074 de 2015. Deben completarse con la identidad, NIT, domicilio y canal del responsable, además de revisión de abogado colombiano antes de captar datos reales. Los datos de salud son sensibles y su suministro es facultativo; el MVP exige autorización explícita y separada.

## Estado

MVP técnico demostrable. No integra todavía portales de EPS, pagos, WhatsApp ni automatización de trámites; esas capacidades están priorizadas en el backlog.

