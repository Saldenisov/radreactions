# WARP.md - RadReactions Platform Documentation

## 📋 Project Overview

**RadReactions** is an open platform for digitizing, curating, validating, and publishing rate constants for aqueous radical reactions. The project is initially based on the Buxton Critical Review of Rate Constants for Reactions of Hydrated Electrons, Hydrogen Atoms and Hydroxyl Radicals in Aqueous Solution (DOI: 10.1063/1.555805).

### 🎯 Purpose
- Extract and digitize chemical reaction data from table images
- Provide collaborative validation workflow for OCR results
- Generate reproducible artifacts (TSV, LaTeX, PDF)
- Maintain a searchable SQLite database with full-text search
- Publish validated rate constants for scientific research

### 🏗️ Architecture
- **Frontend**: Streamlit web application
- **Database**: SQLite with FTS5 (Full-Text Search)
- **Data Pipeline**: Images → OCR → TSV → LaTeX → PDF → Database
- **Authentication**: Bcrypt-secured user management
- **Deployment**: Docker + Docker Compose, Railway-ready

## 📁 Project Structure

```
radreactions/
├── 📄 Core Application Files
│   ├── main_app.py              # Main Streamlit application entry point
│   ├── config.py                # Environment and path configuration
│   ├── reactions_db.py          # Database schema, operations, and search
│   ├── auth_db.py               # User authentication and session management
│   ├── validate_embedded.py     # OCR validation interface
│   └── import_reactions.py      # CSV/TSV data import functions
│
├── 🧰 Utility Modules
│   ├── pdf_utils.py             # LaTeX/PDF generation and chemical formula processing
│   ├── tsv_utils.py             # TSV file correction and chemical notation handling
│   ├── db_utils.py              # Database utility functions
│   └── simple_tsv_editor.py     # Inline TSV editing interface
│
├── 📊 Data Processing Pages
│   └── pages/
│       └── 99_Admin_Upload_Data.py  # Admin interface for data uploads
│
├── 🔧 Command Line Tools
│   └── tools/
│       ├── rebuild_db.py        # Database rebuilding from validated sources
│       ├── check_db.py          # Database integrity checking
│       ├── reset_db.py          # Database reset utilities
│       ├── recompute_canonical.py  # Reaction formula canonicalization
│       ├── reindex_fts.py       # Full-text search reindexing
│       └── wipe_db.py           # Database cleanup utilities
│
├── 🧪 Testing
│   └── tests/
│       ├── conftest.py          # Pytest configuration
│       ├── test_canonicalization.py  # Formula canonicalization tests
│       ├── test_fast_import.py  # Data import testing
│       ├── test_import_parsing.py    # Import parsing tests
│       ├── test_paths_and_search.py # Path resolution and search tests
│       ├── test_pdf_utils.py    # PDF generation tests
│       ├── test_rebuild_db.py   # Database rebuild tests
│       └── test_tsv_utils.py    # TSV utilities tests
│
├── 🚀 Deployment
│   ├── Dockerfile              # Container image definition
│   ├── docker-compose.yml      # Local deployment configuration
│   ├── railway.toml            # Railway deployment configuration
│   └── test-docker.bat         # Windows Docker testing script
│
├── ⚙️ Configuration
│   ├── pyproject.toml          # Python project configuration, linting, typing
│   ├── requirements.txt        # Production dependencies
│   ├── requirements-dev.txt    # Development dependencies
│   ├── pytest.ini             # Pytest configuration
│   └── .streamlit/config.toml  # Streamlit configuration
│
└── 📚 Documentation
    ├── README.md               # Project overview and quick start
    ├── FUTURE.md               # Roadmap and planned features
    └── WARP.md                 # This comprehensive documentation
```

## 🔄 Data Processing Workflow

### 1. **Image Processing Pipeline**
```
Table Images (.png) → OCR → TSV/CSV → LaTeX → PDF → SQLite Database
```

### 2. **Validation Workflow**
1. **Image Display**: Show original table images alongside extracted data
2. **TSV Editing**: Inline correction of OCR results with chemical notation support
3. **LaTeX Generation**: Automatic conversion to publication-ready LaTeX
4. **PDF Compilation**: XeLaTeX compilation for visual verification
5. **Database Import**: Validated data imported into searchable database
6. **Collaborative Tracking**: User-based validation metadata

### 3. **Data Model**

#### Database Schema
- **`reactions`**: Core table storing reaction metadata
  - `id`: Primary key
  - `table_no`: Source table number (5-9)
  - `table_category`: Descriptive category
  - `buxton_reaction_number`: Original Buxton numbering
  - `reaction_name`: Human-readable reaction name
  - `formula_latex`: LaTeX chemical formula
  - `formula_canonical`: Normalized formula for search/dedup
  - `reactants/products`: Parsed reaction components
  - `reactant_species/product_species`: JSON arrays of species
  - `notes`: Additional reaction notes
  - `png_path`: Source image path
  - `source_path`: CSV/TSV source path
  - `validated`: Boolean validation status
  - `validated_by/validated_at`: Validation metadata
  - `skipped`: Boolean skip status
  - Timestamps: `created_at`, `updated_at`

- **`measurements`**: Rate constant measurements
  - `reaction_id`: Foreign key to reactions
  - `pH`: Solution pH value
  - `temperature_C`: Temperature in Celsius
  - `rate_value`: Raw rate constant string
  - `rate_value_num`: Parsed numeric rate value
  - `rate_units`: Units of measurement
  - `method`: Experimental method
  - `conditions`: Additional experimental conditions
  - `reference_id`: Foreign key to references
  - `references_raw`: Raw reference text
  - `source_path`: Source file path
  - `page_info`: Page/location information

- **`references_map`**: Literature references
  - `buxton_code`: Buxton reference codes
  - `citation_text`: Full citation
  - `doi`: Digital Object Identifier
  - `doi_status`: DOI validation status
  - `raw_text`: Original reference text
  - `notes`: Additional reference notes

- **`reactions_fts`**: Full-text search index (FTS5)
  - Indexes: `reaction_name`, `formula_canonical`, `notes`

## 🧩 Key Components

### Core Modules

#### `main_app.py` - Application Entry Point
- **Authentication Integration**: Session-based login/logout
- **Navigation System**: Page mode switching (main/validate/profile)
- **Database Statistics**: Real-time validation progress tracking
- **Search Interface**: Public and authenticated search functionality
- **Admin Tools**: Database rebuilding and maintenance (admin-only)
- **Activity Logging**: User action tracking

#### `reactions_db.py` - Database Layer
- **Schema Management**: Database initialization and migrations
- **Formula Canonicalization**: LaTeX chemical formula normalization
- **CRUD Operations**: Reaction and measurement management
- **Search Functions**: FTS5-powered full-text search
- **Validation Tracking**: User-based validation state management
- **Statistics Generation**: Per-table and global metrics

#### `auth_db.py` - Authentication System
- **User Management**: SQLite-based user storage
- **Password Security**: Bcrypt hashing with salt
- **Session Handling**: Token-based persistent sessions
- **Role-Based Access**: Admin/user permission levels
- **Registration System**: New user request workflow

#### `validate_embedded.py` - Validation Interface
- **Image Display**: Original table image viewing
- **TSV Editing**: Inline correction with syntax highlighting
- **LaTeX Preview**: Real-time LaTeX compilation
- **PDF Generation**: XeLaTeX-based PDF creation
- **Validation Tracking**: User-based validation state
- **Batch Processing**: Multi-file validation workflows

### Utility Modules

#### `pdf_utils.py` - Document Generation
- **LaTeX Processing**: Chemical formula LaTeX normalization
- **mhchem Integration**: Chemical equation formatting
- **PDF Compilation**: XeLaTeX document generation
- **Template System**: Structured LaTeX document templates
- **Error Handling**: Compilation error reporting and recovery

#### `tsv_utils.py` - Data Processing
- **Chemical Notation**: Radical dot and charge notation correction
- **TSV Validation**: Format checking and repair
- **Formula Parsing**: Chemical equation component extraction
- **Unicode Handling**: Proper chemical symbol encoding

#### `import_reactions.py` - Data Import
- **CSV/TSV Parsing**: Tab-delimited file processing
- **Idempotent Imports**: Safe re-import without duplication
- **Reference Linking**: Buxton code to DOI mapping
- **Rate Value Parsing**: Scientific notation handling
- **Measurement Association**: Multi-measurement per reaction support

### Command Line Tools

#### `tools/rebuild_db.py` - Database Management
- **Offline Building**: Atomic database reconstruction
- **Validation Filtering**: Import only validated entries
- **Safe Swapping**: Zero-downtime database updates
- **Progress Tracking**: Detailed rebuild status reporting

#### `tools/csv_ai_corrector.py` - AI-Assisted Correction
- **OpenAI Integration**: GPT-4 powered chemistry correction
- **Formula Validation**: Chemical equation balancing
- **Batch Processing**: Automated correction workflows
- **Human Review**: AI suggestions with manual approval

## 🚀 Deployment Guide

### Local Development
```bash
# Prerequisites: Python 3.11+, LaTeX/XeLaTeX
pip install -r requirements.txt
streamlit run main_app.py
```

### Docker Deployment
```bash
# Build and run with persistent data volume
docker-compose up --build
```

### Railway Deployment
- Configured via `railway.toml`
- Automatic builds from Git repository
- Persistent volume mounting for data
- Environment variable configuration

### Environment Variables
- `DATA_DIR`: Base directory for data storage (overrides auto-detection)
- `BASE_DIR`: Legacy base directory variable
- `USERS_DB_PATH`: Custom user database location
- `STREAMLIT_*`: Streamlit server configuration

## 🔍 Search Capabilities

### Full-Text Search (FTS5)
- **Indexed Fields**: Reaction names, canonical formulas, notes
- **Query Types**: Simple text, phrase matching, Boolean operations
- **Performance**: Optimized for large datasets with instant results
- **Filtering**: Table-based filtering (Tables 5-9)

### Search Interface
- **Public Access**: Basic search functionality for all users
- **Authenticated Search**: Advanced filters and full database access
- **Result Display**: Expandable results with detailed metadata
- **Export Options**: Search results export capabilities

## 🧪 Testing Strategy

### Test Coverage
- **Unit Tests**: Core functionality validation
- **Integration Tests**: Database and file system operations
- **End-to-End Tests**: Complete workflow validation
- **Performance Tests**: Database query optimization

### Test Categories
- **Canonicalization**: Chemical formula normalization
- **Import/Export**: Data pipeline integrity
- **PDF Generation**: LaTeX compilation and error handling
- **Database Operations**: CRUD and search functionality
- **Path Resolution**: Cross-platform file handling

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test category
pytest tests/test_canonicalization.py
```

## 🔧 Development Workflow

### Code Quality
- **Linting**: Ruff for Python code style and errors
- **Type Checking**: MyPy for static type analysis
- **Formatting**: Automatic code formatting with Ruff
- **Pre-commit**: Automated quality checks

### Git Workflow
- **Git LFS**: Large file storage for images and datasets
- **Feature Branches**: Isolated development workflow
- **Code Review**: Pull request based development
- **Automated Testing**: CI/CD pipeline integration

### Database Management
- **Migrations**: Automatic schema updates
- **Backups**: Regular database snapshots
- **Performance Monitoring**: Query optimization tracking
- **Integrity Checks**: Automated validation of database state

## 📊 Performance Considerations

### Database Optimization
- **Indexes**: Strategic indexing for common queries
- **FTS5**: Full-text search for rapid text queries
- **Connection Pooling**: Efficient database connection management
- **WAL Mode**: Write-Ahead Logging for concurrent access

### File System
- **Path Canonicalization**: Consistent cross-platform path handling
- **Large File Handling**: Git LFS for images and datasets
- **Caching**: Intelligent caching of generated artifacts
- **Cleanup**: Automatic temporary file management

### Memory Management
- **Streamlit Sessions**: Efficient session state management
- **Image Loading**: On-demand image loading and display
- **Database Queries**: Paginated results for large datasets
- **PDF Generation**: Memory-efficient LaTeX compilation

## 🛠️ Maintenance Tasks

### Regular Maintenance
- **Database Rebuilds**: Periodic full database reconstruction
- **FTS Reindexing**: Full-text search index optimization
- **Log Rotation**: Application log management
- **Cache Cleanup**: Temporary file and cache cleanup

### Monitoring
- **Database Size**: Monitor database growth and performance
- **User Activity**: Track validation progress and user engagement
- **Error Reporting**: Automated error detection and reporting
- **Performance Metrics**: Response time and resource utilization

### Backup Strategy
- **Database Backups**: Regular SQLite database snapshots
- **Data Volume Backups**: Complete data directory backups
- **Version Control**: Source code and configuration versioning
- **Recovery Testing**: Regular backup restoration verification

## 🗺️ Future Roadmap

### Short Term (Next Release)
- **API Development**: RESTful API for programmatic access
- **DOI Resolution**: Automatic DOI validation and enrichment
- **Export Formats**: Additional data export options (JSON, XML)
- **Mobile Responsiveness**: Improved mobile interface

### Medium Term (6 months)
- **Table Expansion**: Support for additional Buxton tables
- **Advanced Search**: Chemical structure-based search
- **Data Visualization**: Interactive charts and graphs
- **User Analytics**: Detailed validation progress tracking

### Long Term (1+ years)
- **Machine Learning**: AI-powered OCR correction
- **Collaborative Features**: Team-based validation workflows
- **Public API**: Open access API for researchers
- **Data Publishing**: Integration with scientific data repositories

## 🤝 Contributing

### Development Setup
1. Fork the repository
2. Create feature branch
3. Install development dependencies
4. Run tests locally
5. Submit pull request

### Code Standards
- Follow PEP 8 Python style guidelines
- Include type hints for new functions
- Write comprehensive tests for new features
- Update documentation for API changes

### Issue Reporting
- Use GitHub Issues for bug reports
- Provide detailed reproduction steps
- Include environment information
- Attach relevant log files

## 📄 License and Acknowledgments

### License
MIT License - See LICENSE file for details

### Acknowledgments
- **Buxton Critical Review**: Original data source and inspiration
- **Streamlit**: Web application framework
- **SQLite**: Embedded database engine
- **LaTeX Community**: Chemical typesetting standards
- **Open Source Contributors**: Community contributions and feedback

### Data Attribution
Data initially derived from:
*Critical Review of rate constants for hydrated electrons, hydrogen atoms and hydroxyl radicals in aqueous solution*
DOI: 10.1063/1.555805

---

**Last Updated**: January 2025
**Version**: 0.0.0
**Maintainer**: Sergey Denisov (sergey.denisov@universite-paris-saclay.fr)
