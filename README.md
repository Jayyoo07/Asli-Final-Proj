# Remote Employee Equipment Allocation Tracker
*HR, Finance & Compliance &bull; Item 33*

A minimalist, zero-dependency Python application designed to track and manage remote employee hardware setups, inventory allocation, shipment tracking, and return compliance agreements.

---

## Core Workflow

1. **Employee Hardware Request Portal**:
   - Remote employees submit hardware package requirements (e.g., Engineering, Design, Knowledge Worker, or Custom configurations).
   - Captures department, role, remote shipping destination, and digital agreement acknowledgment.
2. **IT Operations Inventory Review**:
   - Live inventory tracking (Laptops, Monitors, Docks, Peripherals) with Asset Tags and serial numbers.
   - IT operations reviews pending requests, matches available stock, assigns specific asset tags, and approves or rejects allocations.
3. **Logistics & Tracking Updates**:
   - IT logs carrier information (FedEx, UPS, DHL, USPS) and consignment tracking IDs.
   - Status transitions from `Pending Review` &rarr; `Approved` &rarr; `Shipped` (In Transit) &rarr; `Delivered`.
4. **Return Agreements & Compliance Logging**:
   - HR & Finance compliance tracking for signed return policy deeds.
   - When an employee offboards or swaps hardware, IT logs return inspection notes, transitions status to `Returned`, and automatically returns assigned asset tags back to available depot inventory.

---

## Technical Design & Minimalism

- **Zero External Dependencies**: Built entirely with Python's standard library (`http.server`, `sqlite3`, `json`, `urllib`, `contextlib`). Runs on any clean Python 3.10+ installation without `pip install`.
- **Clean Architecture**: Concise, production-ready implementation without framework bloat.
- **Embedded Minimalist Interface**: Fast, responsive single-page web UI crafted with semantic HTML, modern typography, and a dark slate aesthetic with real-time feedback.
- **Automated SQLite Persistence**: Automatically initializes tables without mock data on initial startup so all entries entered by users are persisted and retained across server restarts. (An optional `--seed` flag is supported if demo data is desired).

---

## Quickstart

### 1. Launch the Application

```bash
python app.py
```

The application server will start at:
```
http://localhost:8080
```
*(Optionally specify a custom port with the `PORT` environment variable, e.g. `PORT=9000 python app.py`. To populate demo mock data, run `python app.py --seed`)*

### 2. Run the Test Suite

```bash
python test_app.py
```

Runs 10 automated unit and HTTP integration tests validating:
- Clean database schema initialization without mock data
- User data persistence across restarts
- Hardware request submission
- Inventory allocation & tag assignment
- Logistics tracking updates
- Return agreement verification and asset restocking
- Live HTTP endpoints and JSON REST API

---

## REST API Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web application UI |
| `GET` | `/api/stats` | High-level metrics (counts & allocated capital) |
| `GET` | `/api/inventory` | List hardware items (`?status=Available` filter supported) |
| `POST` | `/api/inventory` | Register new equipment item |
| `GET` | `/api/requests` | List allocation requests (`?status=Pending Review` filter supported) |
| `POST` | `/api/requests` | Submit new hardware request |
| `POST` | `/api/requests/<id>/review` | Approve/reject request & allocate asset tags |
| `POST` | `/api/requests/<id>/tracking` | Update carrier, tracking number, and delivery status |
| `POST` | `/api/requests/<id>/return` | Update return agreement record & restock returned hardware |

---

## License
MIT License.
