"""Postgres initialization generator for mcp-trajs2data.

Generates realistic initial database schemas with foreign keys,
diverse data types, and seed-based reproducibility.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class SchemaComplexity(str, Enum):
    """Complexity profiles for generated schemas."""

    SIMPLE = "simple"    # 2-3 tables, basic relationships
    MEDIUM = "medium"    # 4-6 tables, foreign keys
    COMPLEX = "complex"  # 7+ tables, complex relationships


@dataclass
class TableSpec:
    """Specification for a table to be created."""

    name: str
    columns: List[Dict[str, str]]
    foreign_keys: List[Dict[str, str]] = field(default_factory=list)

    def to_init_operation(self) -> Dict[str, Any]:
        """Convert to initialization operation format."""
        column_defs = [f"{col['name']} {col['type']}" for col in self.columns]
        for fk in self.foreign_keys:
            column_defs.append(
                f"FOREIGN KEY ({fk['column']}) REFERENCES {fk['references']}"
            )
        create_sql = f"CREATE TABLE {self.name} ({', '.join(column_defs)})"
        return {"tool": "query", "arguments": {"sql": create_sql}}


@dataclass
class DataSpec:
    """Specification for data to be inserted."""

    table: str
    rows: List[Dict[str, Any]]

    def to_init_operation(self) -> Dict[str, Any]:
        """Convert to initialization operation format."""
        if not self.rows:
            return None

        columns = list(self.rows[0].keys())
        column_str = ", ".join(columns)

        values_list = []
        for row in self.rows:
            values = [self._format_value(row[col]) for col in columns]
            values_list.append(f"({', '.join(values)})")

        insert_sql = f"INSERT INTO {self.table} ({column_str}) VALUES {', '.join(values_list)}"
        return {"tool": "query", "arguments": {"sql": insert_sql}}

    def _format_value(self, value: Any) -> str:
        """Format a value for SQL."""
        if value is None:
            return "NULL"
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        elif isinstance(value, float):
            return f"{value:.2f}"
        else:
            return str(value)


@dataclass
class InitPlan:
    """Plan for initializing a postgres database environment."""

    database: str
    tables: List[TableSpec] = field(default_factory=list)
    data: List[DataSpec] = field(default_factory=list)
    seed: int = 0
    complexity: SchemaComplexity = SchemaComplexity.SIMPLE

    def to_operations(self) -> List[Dict[str, Any]]:
        """Convert to list of initialization operations.

        Returns operations in correct order: tables first, then data.
        """
        operations = []

        # Create tables first
        for table_spec in self.tables:
            operations.append(table_spec.to_init_operation())

        # Insert data
        for data_spec in self.data:
            op = data_spec.to_init_operation()
            if op:
                operations.append(op)

        return operations

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of the init plan."""
        total_rows = sum(len(d.rows) for d in self.data)
        return {
            "database": self.database,
            "seed": self.seed,
            "complexity": self.complexity.value,
            "num_tables": len(self.tables),
            "num_data_specs": len(self.data),
            "total_rows": total_rows,
            "total_operations": len(self.tables) + len(self.data),
        }


# ============================================================
# Theme definitions with structured schemas and relationships
# Each theme defines tables in dependency order (referenced first)
# ============================================================

TABLE_THEMES = {
    "ecommerce": {
        "tables": [
            {
                "name": "categories",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "name", "type": "VARCHAR(100) NOT NULL"},
                    {"name": "description", "type": "TEXT"},
                    {"name": "parent_id", "type": "INTEGER"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "first_name", "type": "VARCHAR(50) NOT NULL"},
                    {"name": "last_name", "type": "VARCHAR(50) NOT NULL"},
                    {"name": "email", "type": "VARCHAR(100) UNIQUE NOT NULL"},
                    {"name": "phone", "type": "VARCHAR(20)"},
                    {"name": "city", "type": "VARCHAR(80)"},
                    {"name": "country", "type": "VARCHAR(60)"},
                    {"name": "registered_at", "type": "TIMESTAMP DEFAULT NOW()"},
                    {"name": "is_active", "type": "BOOLEAN DEFAULT TRUE"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "products",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "name", "type": "VARCHAR(200) NOT NULL"},
                    {"name": "category_id", "type": "INTEGER"},
                    {"name": "price", "type": "NUMERIC(10,2) NOT NULL"},
                    {"name": "stock_quantity", "type": "INTEGER DEFAULT 0"},
                    {"name": "rating", "type": "NUMERIC(2,1)"},
                    {"name": "created_at", "type": "TIMESTAMP DEFAULT NOW()"},
                ],
                "foreign_keys": [{"column": "category_id", "references": "categories(id)"}],
            },
            {
                "name": "orders",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "customer_id", "type": "INTEGER NOT NULL"},
                    {"name": "order_date", "type": "DATE NOT NULL"},
                    {"name": "status", "type": "VARCHAR(20) DEFAULT 'pending'"},
                    {"name": "total_amount", "type": "NUMERIC(12,2)"},
                    {"name": "shipping_address", "type": "TEXT"},
                ],
                "foreign_keys": [{"column": "customer_id", "references": "customers(id)"}],
            },
            {
                "name": "order_items",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "order_id", "type": "INTEGER NOT NULL"},
                    {"name": "product_id", "type": "INTEGER NOT NULL"},
                    {"name": "quantity", "type": "INTEGER NOT NULL"},
                    {"name": "unit_price", "type": "NUMERIC(10,2) NOT NULL"},
                ],
                "foreign_keys": [
                    {"column": "order_id", "references": "orders(id)"},
                    {"column": "product_id", "references": "products(id)"},
                ],
            },
            {
                "name": "reviews",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "product_id", "type": "INTEGER NOT NULL"},
                    {"name": "customer_id", "type": "INTEGER NOT NULL"},
                    {"name": "rating", "type": "INTEGER CHECK (rating BETWEEN 1 AND 5)"},
                    {"name": "comment", "type": "TEXT"},
                    {"name": "review_date", "type": "DATE"},
                ],
                "foreign_keys": [
                    {"column": "product_id", "references": "products(id)"},
                    {"column": "customer_id", "references": "customers(id)"},
                ],
            },
        ],
    },
    "education": {
        "tables": [
            {
                "name": "departments",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "name", "type": "VARCHAR(100) NOT NULL"},
                    {"name": "building", "type": "VARCHAR(50)"},
                    {"name": "budget", "type": "NUMERIC(12,2)"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "teachers",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "first_name", "type": "VARCHAR(50) NOT NULL"},
                    {"name": "last_name", "type": "VARCHAR(50) NOT NULL"},
                    {"name": "email", "type": "VARCHAR(100) UNIQUE"},
                    {"name": "department_id", "type": "INTEGER"},
                    {"name": "hire_date", "type": "DATE"},
                    {"name": "salary", "type": "NUMERIC(10,2)"},
                ],
                "foreign_keys": [{"column": "department_id", "references": "departments(id)"}],
            },
            {
                "name": "courses",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "code", "type": "VARCHAR(20) UNIQUE NOT NULL"},
                    {"name": "title", "type": "VARCHAR(200) NOT NULL"},
                    {"name": "credits", "type": "INTEGER NOT NULL"},
                    {"name": "department_id", "type": "INTEGER"},
                    {"name": "teacher_id", "type": "INTEGER"},
                    {"name": "max_enrollment", "type": "INTEGER DEFAULT 40"},
                ],
                "foreign_keys": [
                    {"column": "department_id", "references": "departments(id)"},
                    {"column": "teacher_id", "references": "teachers(id)"},
                ],
            },
            {
                "name": "students",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "first_name", "type": "VARCHAR(50) NOT NULL"},
                    {"name": "last_name", "type": "VARCHAR(50) NOT NULL"},
                    {"name": "email", "type": "VARCHAR(100) UNIQUE"},
                    {"name": "date_of_birth", "type": "DATE"},
                    {"name": "gpa", "type": "NUMERIC(3,2)"},
                    {"name": "enrollment_year", "type": "INTEGER"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "enrollments",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "student_id", "type": "INTEGER NOT NULL"},
                    {"name": "course_id", "type": "INTEGER NOT NULL"},
                    {"name": "semester", "type": "VARCHAR(20) NOT NULL"},
                    {"name": "grade", "type": "VARCHAR(2)"},
                    {"name": "enrolled_at", "type": "TIMESTAMP DEFAULT NOW()"},
                ],
                "foreign_keys": [
                    {"column": "student_id", "references": "students(id)"},
                    {"column": "course_id", "references": "courses(id)"},
                ],
            },
        ],
    },
    "hr": {
        "tables": [
            {
                "name": "departments",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "name", "type": "VARCHAR(100) NOT NULL"},
                    {"name": "location", "type": "VARCHAR(100)"},
                    {"name": "budget", "type": "NUMERIC(14,2)"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "positions",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "title", "type": "VARCHAR(100) NOT NULL"},
                    {"name": "min_salary", "type": "NUMERIC(10,2)"},
                    {"name": "max_salary", "type": "NUMERIC(10,2)"},
                    {"name": "level", "type": "VARCHAR(20)"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "employees",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "first_name", "type": "VARCHAR(50) NOT NULL"},
                    {"name": "last_name", "type": "VARCHAR(50) NOT NULL"},
                    {"name": "email", "type": "VARCHAR(100) UNIQUE"},
                    {"name": "department_id", "type": "INTEGER"},
                    {"name": "position_id", "type": "INTEGER"},
                    {"name": "manager_id", "type": "INTEGER"},
                    {"name": "hire_date", "type": "DATE NOT NULL"},
                    {"name": "salary", "type": "NUMERIC(10,2) NOT NULL"},
                    {"name": "is_active", "type": "BOOLEAN DEFAULT TRUE"},
                ],
                "foreign_keys": [
                    {"column": "department_id", "references": "departments(id)"},
                    {"column": "position_id", "references": "positions(id)"},
                ],
            },
            {
                "name": "projects",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "name", "type": "VARCHAR(200) NOT NULL"},
                    {"name": "department_id", "type": "INTEGER"},
                    {"name": "start_date", "type": "DATE"},
                    {"name": "end_date", "type": "DATE"},
                    {"name": "budget", "type": "NUMERIC(14,2)"},
                    {"name": "status", "type": "VARCHAR(20) DEFAULT 'active'"},
                ],
                "foreign_keys": [{"column": "department_id", "references": "departments(id)"}],
            },
            {
                "name": "project_assignments",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "employee_id", "type": "INTEGER NOT NULL"},
                    {"name": "project_id", "type": "INTEGER NOT NULL"},
                    {"name": "role", "type": "VARCHAR(50)"},
                    {"name": "hours_allocated", "type": "INTEGER"},
                    {"name": "assigned_at", "type": "DATE"},
                ],
                "foreign_keys": [
                    {"column": "employee_id", "references": "employees(id)"},
                    {"column": "project_id", "references": "projects(id)"},
                ],
            },
            {
                "name": "salary_history",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "employee_id", "type": "INTEGER NOT NULL"},
                    {"name": "old_salary", "type": "NUMERIC(10,2)"},
                    {"name": "new_salary", "type": "NUMERIC(10,2) NOT NULL"},
                    {"name": "change_date", "type": "DATE NOT NULL"},
                    {"name": "reason", "type": "VARCHAR(100)"},
                ],
                "foreign_keys": [{"column": "employee_id", "references": "employees(id)"}],
            },
        ],
    },
    "social": {
        "tables": [
            {
                "name": "users",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "username", "type": "VARCHAR(50) UNIQUE NOT NULL"},
                    {"name": "display_name", "type": "VARCHAR(100)"},
                    {"name": "email", "type": "VARCHAR(100) UNIQUE NOT NULL"},
                    {"name": "bio", "type": "TEXT"},
                    {"name": "follower_count", "type": "INTEGER DEFAULT 0"},
                    {"name": "joined_at", "type": "TIMESTAMP DEFAULT NOW()"},
                    {"name": "is_verified", "type": "BOOLEAN DEFAULT FALSE"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "posts",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "author_id", "type": "INTEGER NOT NULL"},
                    {"name": "title", "type": "VARCHAR(300)"},
                    {"name": "content", "type": "TEXT NOT NULL"},
                    {"name": "like_count", "type": "INTEGER DEFAULT 0"},
                    {"name": "view_count", "type": "INTEGER DEFAULT 0"},
                    {"name": "published_at", "type": "TIMESTAMP"},
                    {"name": "is_pinned", "type": "BOOLEAN DEFAULT FALSE"},
                ],
                "foreign_keys": [{"column": "author_id", "references": "users(id)"}],
            },
            {
                "name": "comments",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "post_id", "type": "INTEGER NOT NULL"},
                    {"name": "author_id", "type": "INTEGER NOT NULL"},
                    {"name": "content", "type": "TEXT NOT NULL"},
                    {"name": "created_at", "type": "TIMESTAMP DEFAULT NOW()"},
                ],
                "foreign_keys": [
                    {"column": "post_id", "references": "posts(id)"},
                    {"column": "author_id", "references": "users(id)"},
                ],
            },
            {
                "name": "likes",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "user_id", "type": "INTEGER NOT NULL"},
                    {"name": "post_id", "type": "INTEGER NOT NULL"},
                    {"name": "created_at", "type": "TIMESTAMP DEFAULT NOW()"},
                ],
                "foreign_keys": [
                    {"column": "user_id", "references": "users(id)"},
                    {"column": "post_id", "references": "posts(id)"},
                ],
            },
            {
                "name": "followers",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "follower_id", "type": "INTEGER NOT NULL"},
                    {"name": "following_id", "type": "INTEGER NOT NULL"},
                    {"name": "followed_at", "type": "TIMESTAMP DEFAULT NOW()"},
                ],
                "foreign_keys": [
                    {"column": "follower_id", "references": "users(id)"},
                    {"column": "following_id", "references": "users(id)"},
                ],
            },
        ],
    },
    "inventory": {
        "tables": [
            {
                "name": "suppliers",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "company_name", "type": "VARCHAR(200) NOT NULL"},
                    {"name": "contact_name", "type": "VARCHAR(100)"},
                    {"name": "email", "type": "VARCHAR(100)"},
                    {"name": "phone", "type": "VARCHAR(20)"},
                    {"name": "country", "type": "VARCHAR(60)"},
                    {"name": "rating", "type": "NUMERIC(2,1)"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "warehouses",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "name", "type": "VARCHAR(100) NOT NULL"},
                    {"name": "city", "type": "VARCHAR(80)"},
                    {"name": "capacity", "type": "INTEGER"},
                ],
                "foreign_keys": [],
            },
            {
                "name": "items",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "sku", "type": "VARCHAR(30) UNIQUE NOT NULL"},
                    {"name": "name", "type": "VARCHAR(200) NOT NULL"},
                    {"name": "supplier_id", "type": "INTEGER"},
                    {"name": "unit_cost", "type": "NUMERIC(10,2)"},
                    {"name": "weight_kg", "type": "NUMERIC(8,2)"},
                    {"name": "is_fragile", "type": "BOOLEAN DEFAULT FALSE"},
                ],
                "foreign_keys": [{"column": "supplier_id", "references": "suppliers(id)"}],
            },
            {
                "name": "stock",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "item_id", "type": "INTEGER NOT NULL"},
                    {"name": "warehouse_id", "type": "INTEGER NOT NULL"},
                    {"name": "quantity", "type": "INTEGER NOT NULL DEFAULT 0"},
                    {"name": "last_restocked", "type": "DATE"},
                ],
                "foreign_keys": [
                    {"column": "item_id", "references": "items(id)"},
                    {"column": "warehouse_id", "references": "warehouses(id)"},
                ],
            },
            {
                "name": "purchase_orders",
                "columns": [
                    {"name": "id", "type": "SERIAL PRIMARY KEY"},
                    {"name": "supplier_id", "type": "INTEGER NOT NULL"},
                    {"name": "warehouse_id", "type": "INTEGER NOT NULL"},
                    {"name": "order_date", "type": "DATE NOT NULL"},
                    {"name": "total_cost", "type": "NUMERIC(12,2)"},
                    {"name": "status", "type": "VARCHAR(20) DEFAULT 'pending'"},
                ],
                "foreign_keys": [
                    {"column": "supplier_id", "references": "suppliers(id)"},
                    {"column": "warehouse_id", "references": "warehouses(id)"},
                ],
            },
        ],
    },
}


# Realistic data pools for value generation
_FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Christopher", "Karen",
    "Daniel", "Lisa", "Matthew", "Nancy", "Anthony", "Betty", "Mark", "Helen",
    "Emma", "Oliver", "Sophia", "Liam", "Ava", "Noah", "Isabella", "Lucas",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Lewis",
]
_CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
    "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Seattle",
    "Denver", "Boston", "Nashville", "Portland", "London", "Paris", "Berlin",
    "Tokyo", "Sydney", "Toronto", "Singapore", "Shanghai", "Mumbai", "Dubai",
]
_COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Germany", "France",
    "Japan", "Australia", "China", "India", "Brazil", "Singapore", "UAE",
]
_PRODUCT_NAMES = [
    "Wireless Headphones", "USB-C Cable", "Laptop Stand", "Mechanical Keyboard",
    "Webcam HD", "Portable Charger", "Mouse Pad XL", "Monitor Light Bar",
    "Desk Organizer", "Bluetooth Speaker", "Phone Case", "Screen Protector",
    "External SSD 1TB", "Ergonomic Chair", "Standing Desk Mat", "Cable Clips",
    "Notebook A5", "Pen Set", "Water Bottle", "Backpack Pro",
]
_CATEGORY_NAMES = [
    "Electronics", "Accessories", "Office Supplies", "Furniture",
    "Audio", "Storage", "Peripherals", "Stationery",
]
_COURSE_CODES = [
    "CS101", "CS201", "CS301", "MATH101", "MATH201", "PHYS101", "PHYS201",
    "ENG101", "ENG201", "BIO101", "CHEM101", "STAT201", "ECON101", "HIST101",
    "ART101", "MUS101", "PSY101", "SOC101", "PHIL101", "CS401",
]
_COURSE_TITLES = [
    "Introduction to Programming", "Data Structures", "Algorithms",
    "Calculus I", "Linear Algebra", "Physics I", "Quantum Mechanics",
    "English Composition", "Creative Writing", "Biology Fundamentals",
    "General Chemistry", "Statistical Methods", "Microeconomics",
    "World History", "Art Appreciation", "Music Theory",
    "Introduction to Psychology", "Sociology 101", "Ethics", "Machine Learning",
]
_DEPT_NAMES = [
    "Computer Science", "Mathematics", "Physics", "Engineering",
    "Marketing", "Finance", "Human Resources", "Operations",
    "Research", "Sales", "Legal", "Customer Support",
]
_POSITION_TITLES = [
    "Software Engineer", "Senior Engineer", "Staff Engineer", "Tech Lead",
    "Product Manager", "Data Analyst", "Designer", "QA Engineer",
    "DevOps Engineer", "Project Manager", "Director", "VP of Engineering",
]
_POST_TITLES = [
    "Getting started with PostgreSQL", "My weekend project",
    "Tips for better SQL queries", "How I learned to code",
    "Review: new laptop setup", "Thoughts on remote work",
    "Best practices for database design", "A beginner's guide to indexing",
    "Why I switched to Linux", "Building my first API",
]
_COMPANY_NAMES = [
    "TechSupply Co.", "Global Parts Inc.", "FastShip Logistics",
    "Quality Materials Ltd.", "Prime Components", "Atlas Manufacturing",
    "Vertex Solutions", "Pinnacle Trading", "Summit Supplies", "CoreTech Inc.",
]
_WAREHOUSE_NAMES = [
    "Main Warehouse", "East Distribution Center", "West Hub",
    "North Storage Facility", "South Depot", "Central Logistics",
]
_SKU_PREFIXES = ["SKU", "ITM", "PRD", "WH", "INV"]
_SEMESTERS = ["Fall 2023", "Spring 2024", "Fall 2024", "Spring 2025"]
_GRADES = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F", None]
_ORDER_STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled"]
_PROJECT_STATUSES = ["planning", "active", "on_hold", "completed", "cancelled"]
_SALARY_REASONS = ["annual_review", "promotion", "market_adjustment", "role_change"]
_LEVELS = ["junior", "mid", "senior", "lead", "principal"]

class PostgresInitGenerator:
    """Generator for postgres database initialization plans."""

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        self.rng = random.Random(self.seed)
        # Track generated IDs per table for foreign key references
        self._table_row_counts: Dict[str, int] = {}

    def generate_init_plan(
        self, database: str, complexity: str = "simple"
    ) -> InitPlan:
        complexity_enum = SchemaComplexity(complexity)
        size_config = self._get_complexity_config(complexity_enum)

        theme = self.rng.choice(list(TABLE_THEMES.keys()))
        logger.info(f"Selected theme: {theme}")

        tables = self._generate_tables(theme, size_config)
        data = self._generate_data(tables, theme, size_config)

        plan = InitPlan(
            database=database, tables=tables, data=data,
            seed=self.seed, complexity=complexity_enum,
        )
        logger.info(f"Generated init plan: {plan.get_summary()}")
        return plan

    def _get_complexity_config(self, complexity: SchemaComplexity) -> Dict[str, Any]:
        return {
            SchemaComplexity.SIMPLE: {"num_tables": (2, 3), "rows_per_table": (8, 20)},
            SchemaComplexity.MEDIUM: {"num_tables": (3, 5), "rows_per_table": (15, 40)},
            SchemaComplexity.COMPLEX: {"num_tables": (4, 6), "rows_per_table": (25, 60)},
        }[complexity]

    def _generate_tables(
        self, theme: str, size_config: Dict[str, Any]
    ) -> List[TableSpec]:
        """Select tables from theme in dependency order."""
        theme_tables = TABLE_THEMES[theme]["tables"]
        min_t, max_t = size_config["num_tables"]
        num_tables = min(self.rng.randint(min_t, max_t), len(theme_tables))

        # Always include tables in dependency order (earlier tables first)
        selected = theme_tables[:num_tables]

        tables = []
        selected_names = {t["name"] for t in selected}
        for tdef in selected:
            # Only include foreign keys whose referenced table is also selected
            fks = [
                fk for fk in tdef["foreign_keys"]
                if fk["references"].split("(")[0] in selected_names
            ]
            tables.append(TableSpec(
                name=tdef["name"],
                columns=list(tdef["columns"]),
                foreign_keys=fks,
            ))
        return tables

    def _generate_data(
        self, tables: List[TableSpec], theme: str, size_config: Dict[str, Any]
    ) -> List[DataSpec]:
        """Generate realistic data respecting foreign key constraints."""
        data_specs = []
        min_rows, max_rows = size_config["rows_per_table"]
        self._table_row_counts = {}

        for table in tables:
            num_rows = self.rng.randint(min_rows, max_rows)
            # Junction tables get fewer rows
            if len(table.foreign_keys) >= 2:
                num_rows = min(num_rows, max_rows // 2)

            rows = []
            for i in range(num_rows):
                row = self._generate_row(table, i, theme)
                rows.append(row)

            self._table_row_counts[table.name] = num_rows
            data_specs.append(DataSpec(table=table.name, rows=rows))

        return data_specs

    def _generate_row(
        self, table: TableSpec, row_idx: int, theme: str
    ) -> Dict[str, Any]:
        """Generate a single row with context-aware values."""
        row = {}
        fk_columns = {fk["column"]: fk["references"] for fk in table.foreign_keys}

        for col in table.columns:
            name = col["name"]
            ctype = col["type"]

            # Skip SERIAL columns (auto-generated)
            if "SERIAL" in ctype:
                continue

            # Foreign key columns: reference valid IDs
            if name in fk_columns:
                ref_table = fk_columns[name].split("(")[0]
                max_id = self._table_row_counts.get(ref_table, 10)
                row[name] = self.rng.randint(1, max(1, max_id))
                continue

            row[name] = self._generate_value(name, ctype, row_idx, table.name)

        return row

    def _generate_value(
        self, col_name: str, col_type: str, row_idx: int, table_name: str
    ) -> Any:
        """Generate a realistic value based on column name and type."""
        cn = col_name.lower()

        # --- VARCHAR / TEXT ---
        if "VARCHAR" in col_type or "TEXT" in col_type:
            if cn == "first_name":
                return self.rng.choice(_FIRST_NAMES)
            if cn == "last_name":
                return self.rng.choice(_LAST_NAMES)
            if cn in ("name", "display_name", "company_name"):
                if table_name in ("categories",):
                    return self.rng.choice(_CATEGORY_NAMES)
                if table_name in ("departments",):
                    return self.rng.choice(_DEPT_NAMES)
                if table_name in ("products", "items"):
                    return self.rng.choice(_PRODUCT_NAMES)
                if table_name in ("projects",):
                    return f"Project {self.rng.choice(['Alpha','Beta','Gamma','Delta','Epsilon','Zeta'])} {row_idx+1}"
                if table_name in ("warehouses",):
                    return self.rng.choice(_WAREHOUSE_NAMES)
                if table_name in ("suppliers",):
                    return self.rng.choice(_COMPANY_NAMES)
                return f"{self.rng.choice(_FIRST_NAMES)} {self.rng.choice(_LAST_NAMES)}"
            if cn == "username":
                return f"{self.rng.choice(_FIRST_NAMES).lower()}{self.rng.randint(1, 999)}"
            if cn == "email":
                fn = self.rng.choice(_FIRST_NAMES).lower()
                ln = self.rng.choice(_LAST_NAMES).lower()
                domain = self.rng.choice(["gmail.com", "outlook.com", "company.com", "example.org"])
                return f"{fn}.{ln}{row_idx}@{domain}"
            if cn == "phone" or cn == "contact_phone":
                return f"+1-{self.rng.randint(200,999)}-{self.rng.randint(100,999)}-{self.rng.randint(1000,9999)}"
            if cn in ("city",):
                return self.rng.choice(_CITIES)
            if cn in ("country",):
                return self.rng.choice(_COUNTRIES)
            if cn in ("title",):
                if table_name in ("positions",):
                    return self.rng.choice(_POSITION_TITLES)
                if table_name in ("posts",):
                    return self.rng.choice(_POST_TITLES)
                if table_name in ("courses",):
                    return self.rng.choice(_COURSE_TITLES)
                return self.rng.choice(_POSITION_TITLES)
            if cn == "code":
                return self.rng.choice(_COURSE_CODES) + f"-{row_idx:02d}"
            if cn == "sku":
                prefix = self.rng.choice(_SKU_PREFIXES)
                return f"{prefix}-{row_idx+1:04d}"
            if cn == "status":
                if table_name in ("orders", "purchase_orders"):
                    return self.rng.choice(_ORDER_STATUSES)
                return self.rng.choice(_PROJECT_STATUSES)
            if cn == "semester":
                return self.rng.choice(_SEMESTERS)
            if cn == "grade":
                return self.rng.choice(_GRADES)
            if cn == "role":
                return self.rng.choice(["lead", "member", "reviewer", "contributor"])
            if cn == "level":
                return self.rng.choice(_LEVELS)
            if cn == "reason":
                return self.rng.choice(_SALARY_REASONS)
            if cn in ("bio", "description", "content", "comment", "shipping_address"):
                return f"Sample {cn} text for row {row_idx + 1}"
            if cn == "building":
                return f"Building {self.rng.choice(['A','B','C','D','E'])}"
            if cn == "location":
                return self.rng.choice(_CITIES)
            if cn == "contact_name":
                return f"{self.rng.choice(_FIRST_NAMES)} {self.rng.choice(_LAST_NAMES)}"
            return f"{cn}_{row_idx}"

        # --- NUMERIC / DECIMAL ---
        if "NUMERIC" in col_type:
            if cn in ("price", "unit_price", "unit_cost", "total_amount", "total_cost"):
                return round(self.rng.uniform(5.0, 500.0), 2)
            if cn in ("salary", "old_salary", "new_salary", "min_salary", "max_salary"):
                return round(self.rng.uniform(40000, 150000), 2)
            if cn in ("budget",):
                return round(self.rng.uniform(50000, 2000000), 2)
            if cn in ("rating",):
                return round(self.rng.uniform(1.0, 5.0), 1)
            if cn in ("gpa",):
                return round(self.rng.uniform(2.0, 4.0), 2)
            if cn in ("weight_kg",):
                return round(self.rng.uniform(0.1, 50.0), 2)
            return round(self.rng.uniform(1.0, 1000.0), 2)

        # --- INTEGER ---
        if "INTEGER" in col_type and "SERIAL" not in col_type:
            if cn in ("credits",):
                return self.rng.choice([1, 2, 3, 4])
            if cn in ("max_enrollment",):
                return self.rng.choice([20, 30, 40, 50, 60])
            if cn in ("enrollment_year",):
                return self.rng.randint(2020, 2025)
            if cn in ("stock_quantity", "quantity"):
                return self.rng.randint(0, 500)
            if cn in ("capacity",):
                return self.rng.randint(1000, 50000)
            if cn in ("hours_allocated",):
                return self.rng.randint(10, 160)
            if cn in ("follower_count", "like_count", "view_count"):
                return self.rng.randint(0, 10000)
            if cn == "rating":
                return self.rng.randint(1, 5)
            if cn == "parent_id":
                return None  # top-level categories
            return self.rng.randint(1, 100)

        # --- BOOLEAN ---
        if "BOOLEAN" in col_type:
            return self.rng.choice([True, False])

        # --- DATE ---
        if col_type == "DATE" or "DATE" in col_type and "TIMESTAMP" not in col_type:
            year = self.rng.randint(2022, 2025)
            month = self.rng.randint(1, 12)
            day = self.rng.randint(1, 28)
            return f"{year}-{month:02d}-{day:02d}"

        # --- TIMESTAMP ---
        if "TIMESTAMP" in col_type:
            year = self.rng.randint(2023, 2025)
            month = self.rng.randint(1, 12)
            day = self.rng.randint(1, 28)
            hour = self.rng.randint(0, 23)
            minute = self.rng.randint(0, 59)
            return f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00"

        return None


# Utility functions for pipeline compatibility
async def execute_init_plan(plan: InitPlan, mcp_client) -> List[Dict[str, Any]]:
    """Execute an initialization plan using MCP client.

    Args:
        plan: InitPlan to execute
        mcp_client: MCP client for executing operations

    Returns:
        List of execution results
    """
    operations = plan.to_operations()
    results = []

    for op in operations:
        try:
            result = await mcp_client.call_tool(op["tool"], op["arguments"])
            results.append({"success": True, "operation": op, "result": result})
        except Exception as e:
            logger.error(f"Failed to execute operation {op}: {e}")
            results.append({"success": False, "operation": op, "error": str(e)})

    return results


def init_plan_to_operations(plan: InitPlan) -> List[Dict[str, Any]]:
    """Convert InitPlan to list of operations for metadata.

    Args:
        plan: InitPlan to convert

    Returns:
        List of operation dictionaries
    """
    return plan.to_operations()

