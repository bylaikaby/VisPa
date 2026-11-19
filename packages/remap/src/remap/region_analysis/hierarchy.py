"""Atlas hierarchy: ARM key levels and CHARM/SARM parent tables.

Version: 0.1.0.dev32 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-10: CHARM/SARM parent tables moved in from hierarchy_table.py. ARM key still repeats a label only inside its declared levels.
Status: candidate
"""

from collections import defaultdict
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


class RegionHierarchy:
    """
    ARM label availability by atlas level, without invented parent paths.

    Parses ARM_key_all.txt format:
    Index\tAbbreviation\tFull_Name\tFirst_Level\tLast_Level
    """

    def __init__(self):
        self.level_map: Dict[str, Dict[int, str]] = {}
        self.index_to_abbr: Dict[int, str] = {}
        self.abbr_to_index: Dict[str, int] = {}

    @classmethod
    def from_file(cls, path: str) -> "RegionHierarchy":
        """Load hierarchy from ARM key file."""
        instance = cls()


        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # Skip header if present
        start_idx = 0
        for i, line in enumerate(lines[:5]):
            if 'Index' in line or 'Abbreviation' in line:
                start_idx = i + 1
                break

        for line in lines[start_idx:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split('\t')
            if len(parts) >= 5:
                try:
                    idx = int(parts[0])
                    abbr = parts[1].strip()
                    full_name = parts[2].strip()
                    first_level = int(parts[3])
                    last_level = int(parts[4])
                    if not 1 <= first_level <= last_level <= 6:
                        raise ValueError("Invalid ARM level availability")

                    # Store index mappings
                    instance.index_to_abbr[idx] = abbr
                    instance.abbr_to_index[abbr] = idx

                    # First/Last_Level specify where this very label occurs;
                    # they are numeric metadata, not L1/L2 parent names.
                    # Parent paths require the CHARM/SARM hierarchy tables.
                    instance.level_map[abbr] = {
                        level: abbr for level in range(first_level, last_level + 1)
                    }

                except (ValueError, IndexError):
                    continue

        return instance

    def get_at_level(self, region: str, level: int) -> Optional[str]:
        """Return this label only at levels where the ARM key declares it."""
        region = str(region).strip()

        if region in self.level_map:
            return self.level_map[region].get(level)

        return None


def _strip_prefix(name: str) -> str:
    """Strip CL_/CR_/SL_/SR_ prefix from region name."""
    if not name:
        return name
    name = str(name).strip()
    for prefix in ['CL_', 'CR_', 'SL_', 'SR_']:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def resolve_to_level(region: str, level: int, hierarchy: Dict = None,
                     hierarchy_table=None) -> Optional[str]:
    """
    Resolve a region to its name at specified hierarchy level.

    Args:
        region: Region name (e.g., "CL_ACC", "1001")
        level: Target hierarchy level (1-6)
        hierarchy: Legacy ARM hierarchy dict {region: {level: parent}}
        hierarchy_table: HierarchyTable or DualHierarchyTable instance

    Returns:
        Region name at target level, or None if not found
    """
    region = str(region).strip()

    # Try hierarchy table first (more reliable with index support)
    if hierarchy_table is not None:
        result = hierarchy_table.get_at_level(region, level)
        if result:
            return result

    # Fallback to legacy hierarchy
    if hierarchy:
        if isinstance(hierarchy, RegionHierarchy):
            return hierarchy.get_at_level(region, level)
        elif isinstance(hierarchy, dict):
            stripped = _strip_prefix(region)
            if stripped in hierarchy:
                return hierarchy[stripped].get(level)

    return None


def _aggregate_length_dict_to_level(length_dict: Dict[str, float],
                                    hierarchy,
                                    level: int,
                                    hierarchy_table=None,
                                    strip_prefixes: bool = False) -> Tuple[Dict[str, float], List[str]]:
    """
    Aggregate region lengths to target hierarchy level.

    Uses hierarchy_table for index-based lookup when available,
    falls back to name-based matching.

    Args:
        length_dict: {region_name_or_index: length}
        hierarchy: Legacy ARM hierarchy dict or RegionHierarchy
        level: Target level (1-6)
        hierarchy_table: HierarchyTable or DualHierarchyTable
        strip_prefixes: If True, remove CL_/CR_/SL_/SR_ prefixes from result

    Returns:
        Tuple of (aggregated_lengths, unmapped_regions)
    """
    aggregated = defaultdict(float)
    unmapped = []

    # Use hierarchy_table if available (more accurate with index support)
    if hierarchy_table is not None:
        return hierarchy_table.aggregate_to_level(length_dict, level, strip_prefixes=strip_prefixes)

    # Fallback to legacy name-based matching
    for region, length in length_dict.items():
        target = resolve_to_level(region, level, hierarchy, None)

        if target:
            if strip_prefixes:
                target = _strip_prefix(target)
            aggregated[target] += length
        else:
            # Try numeric index fallback
            try:
                idx = int(region)
                # If it's a number, we couldn't map it without table
                unmapped.append(region)
            except ValueError:
                # Strip prefix and try again
                base = _strip_prefix(region)
                if base != region:
                    target = resolve_to_level(base, level, hierarchy, None)
                    if target:
                        if strip_prefixes:
                            target = _strip_prefix(target)
                        aggregated[target] += length
                    else:
                        unmapped.append(region)
                else:
                    unmapped.append(region)

    return dict(aggregated), unmapped


def add_soma_hierarchy_column(df, hierarchy, soma_col: str = "Soma_Region",
                               max_level: int = 6,
                               hierarchy_table=None):
    """
    Add hierarchy columns for soma regions.

    Creates columns: Soma_Level_1, Soma_Level_2, ..., Soma_Level_{max_level}

    Args:
        df: DataFrame with soma region column
        hierarchy: RegionHierarchy or dict
        soma_col: Name of soma region column
        max_level: Maximum hierarchy level to create
        hierarchy_table: HierarchyTable for index-based lookup

    Returns:
        Modified DataFrame
    """
    import pandas as pd

    if soma_col not in df.columns:
        return df

    for level in range(1, max_level + 1):
        col_name = f"Soma_Level_{level}"

        results = []
        for soma_region in df[soma_col]:
            resolved = resolve_to_level(soma_region, level, hierarchy, hierarchy_table)
            results.append(resolved if resolved else None)

        df[col_name] = results

    return df


def extract_soma_level(df, level: int = 6) -> pd.Series:
    """
    Extract soma region data at specified hierarchy level.

    Args:
        df: DataFrame with hierarchy columns
        level: Hierarchy level to extract

    Returns:
        Series with region names at specified level
    """
    import pandas as pd

    col_name = f"Soma_Level_{level}"
    if col_name in df.columns:
        return df[col_name]

    # Fallback: use original soma region
    if "Soma_Region" in df.columns:
        return df["Soma_Region"]

    return pd.Series([None] * len(df), index=df.index)


def add_projection_length_hierarchy(df, hierarchy: Dict, base_col: str,
                                    max_level: int = 6,
                                    min_level: int = 1,
                                    hierarchy_table=None) -> Any:
    """
    Add hierarchy columns for projection length data.

    Creates columns: Region_Projection_Length_L1, L2, ... up to max_level

    Args:
        df: DataFrame with projection data
        hierarchy: Legacy ARM hierarchy dict or RegionHierarchy
        base_col: Base column name (e.g., "Region_projection_length")
        max_level: Maximum hierarchy level to create
        min_level: Minimum hierarchy level to create (default 1)
        hierarchy_table: HierarchyTable or DualHierarchyTable for index-based lookup

    Returns:
        Modified DataFrame
    """
    import pandas as pd
    import ast

    def safe_literal_eval(val):
        """Safely evaluate string representation of dict/list."""
        if isinstance(val, dict):
            return val
        if not isinstance(val, str):
            return {}
        if isinstance(val, str):
            try:
                return ast.literal_eval(val)
            except (ValueError, SyntaxError):
                return {}
        return {}

    def aggregate_to_level_safe(length_dict, target_level):
        """Helper to aggregate with error handling."""
        if not length_dict:
            return {}
        agg, _ = _aggregate_length_dict_to_level(
            length_dict, hierarchy, target_level, hierarchy_table, strip_prefixes=False
        )
        return agg

    # Process each level
    for level in range(min_level, max_level + 1):
        col_name = f"Region_Projection_Length_L{level}"

        results = []
        for idx, row in df.iterrows():
            if base_col in row:
                length_dict = safe_literal_eval(row[base_col])
                agg = aggregate_to_level_safe(length_dict, level)
                results.append(agg)
            else:
                results.append({})

        df[col_name] = results

    return df


def add_projection_hierarchy(df, hierarchy, max_level: int = 6,
                              hierarchy_table=None):
    """
    Add projection hierarchy columns (terminal region-based).

    Similar to add_projection_length_hierarchy but for terminal regions.
    Creates columns: Terminal_Level_1, Terminal_Level_2, etc.

    Args:
        df: DataFrame with projection data
        hierarchy: Legacy hierarchy
        max_level: Maximum hierarchy level
        hierarchy_table: HierarchyTable for index-based lookup

    Returns:
        Modified DataFrame
    """
    import pandas as pd
    import ast

    def safe_literal_eval(val):
        if isinstance(val, list):
            return val
        if not isinstance(val, str):
            return []
        if isinstance(val, str):
            try:
                return ast.literal_eval(val)
            except (ValueError, SyntaxError):
                return []
        return []

    terminal_col = "Terminal_Regions"
    if terminal_col not in df.columns:
        return df

    for level in range(1, max_level + 1):
        col_name = f"Terminal_Level_{level}"

        results = []
        for idx, row in df.iterrows():
            terminals = safe_literal_eval(row.get(terminal_col, []))

            resolved = []
            for term in terminals:
                r = resolve_to_level(term, level, hierarchy, hierarchy_table)
                if r and r not in resolved:
                    resolved.append(r)

            results.append(resolved)

        df[col_name] = results

    return df


class HierarchyTable:
    """
    Parses and queries hierarchy CSV files (CHARM/SARM).

    Supports v2 format with columns:
    - Level_1, Level_2, ... Level_6 (full names)
    - Level_1_abbr, Level_2_abbr, ... (abbreviations with prefixes like CL_, SL_)
    - Level_1_index, Level_2_index, ... (numeric indices matching ARM_key_all.txt)

    Builds both:
    - region_paths: abbreviation -> list of region names at each level
    - index_paths: numeric index -> list of region names at each level
    """

    def __init__(self, df: pd.DataFrame = None, name: str = ""):
        self.df = df
        self.name = name
        self.region_paths: Dict[str, List[str]] = {}  # abbr -> path
        self.index_paths: Dict[int, List[str]] = {}   # index -> path
        self.max_level = 0

        if df is not None:
            self._parse_df()

    @staticmethod
    def _detect_level_columns(df: pd.DataFrame) -> Dict[int, str]:
        """Detect level columns (Level_1, L1, etc.) and return {level: column_name}."""
        level_cols = {}

        for col in df.columns:
            col_str = str(col)
            # Match patterns like "Level_1", "Level 1", "L1", "L_1"
            match = re.match(r'^[Ll](?:evel)?[_\s]*(\d+)$', col_str, re.IGNORECASE)
            if match:
                level = int(match.group(1))
                level_cols[level] = col_str

        return level_cols

    def _parse_df(self):
        """Keep explicit level positions and reject conflicting identity paths."""
        df = self.df
        level_cols = self._detect_level_columns(df)
        if not level_cols:
            raise ValueError("Hierarchy table has no level columns")
        if min(level_cols) < 0 or max(level_cols) > 6:
            raise ValueError("Hierarchy levels must be between 0 and 6")
        self.max_level = max(level_cols)
        self._level_start = 0 if 0 in level_cols else 1
        levels = list(range(self._level_start, self.max_level + 1))

        def register(mapping, key, path):
            if key in mapping:
                previous = mapping[key]
                for old, new in zip(previous, path):
                    if old is not None and new is not None and old != new:
                        raise ValueError(f"Conflicting hierarchy paths for {key}")
                mapping[key] = [old if old is not None else new
                                for old, new in zip(previous, path)]
            else:
                mapping[key] = path

        for _, row in df.iterrows():
            row_path, indices = [], []
            for lv in levels:
                abbr = row.get(f"Level_{lv}_abbr")
                if pd.isna(abbr) or not str(abbr).strip():
                    abbr = row.get(level_cols.get(lv))
                    abbr = self._strip_prefix(str(abbr).strip()) if pd.notna(abbr) else None
                row_path.append(str(abbr).strip() if pd.notna(abbr) and str(abbr).strip() else None)
                index = row.get(f"Level_{lv}_index")
                if pd.isna(index):
                    indices.append(None)
                else:
                    numeric = float(index)
                    if not np.isfinite(numeric) or not numeric.is_integer() or numeric <= 0:
                        raise ValueError(f"Invalid hierarchy index {index}")
                    indices.append(int(numeric))
            for pos, name in enumerate(row_path):
                if name is not None:
                    last = max(i for i, value in enumerate(row_path) if value == name)
                    register(self.region_paths, name, row_path[:last+1] + [None]*(len(row_path)-last-1))
            for pos, index in enumerate(indices):
                if index is not None:
                    last = max(i for i, value in enumerate(indices) if value == index)
                    register(self.index_paths, index, row_path[:last+1] + [None]*(len(row_path)-last-1))

    @classmethod
    def from_files(cls, *paths):
        """Load and merge requested files; missing/conflicting inputs fail closed."""
        if not paths:
            raise ValueError("At least one hierarchy file is required")
        tables = [cls.load_file(path) for path in paths]
        return cls(pd.concat([table.df for table in tables], ignore_index=True))

    @staticmethod
    def _strip_prefix(name: str) -> str:
        """Strip CL_/CR_/SL_/SR_ prefix."""
        if not name:
            return name
        name = str(name).strip()
        for prefix in ['CL_', 'CR_', 'SL_', 'SR_']:
            if name.startswith(prefix):
                return name[len(prefix):]
        return name

    def get_path(self, region: str) -> Optional[List[str]]:
        """Get hierarchy path for a region (by name, abbreviation, or index)."""
        region = str(region).strip()

        # Try direct match
        if region in self.region_paths:
            return self.region_paths[region]

        # Try stripped version
        stripped = self._strip_prefix(region)
        if stripped in self.region_paths:
            return self.region_paths[stripped]

        # Try numeric index
        try:
            idx = int(region)
            if idx in self.index_paths:
                return self.index_paths[idx]
        except ValueError:
            pass

        return None

    def get_at_level(self, region: str, level: int) -> Optional[str]:
        """
        Get region name at specified level.

        Args:
            region: Region name, abbreviation, or index
            level: Target level (1-6)

        Returns:
            Region abbreviation at target level, or None
        """
        path = self.get_path(region)
        if path is None:
            return None

        level_idx = level - self._level_start

        if level_idx < 0 or level_idx >= len(path):
            return None

        return path[level_idx]

    def lookup_by_index(self, index: int, level: int = None) -> Optional[Union[str, List[str]]]:
        """
        Lookup region by numeric index.

        Args:
            index: Numeric region index (from ARM_key_all.txt)
            level: If specified, return region at this level; otherwise return full path

        Returns:
            Region name/path or None
        """
        if index not in self.index_paths:
            return None

        path = self.index_paths[index]
        if level is None:
            return path

        level_idx = level - self._level_start

        if level_idx < 0 or level_idx >= len(path):
            return None

        return path[level_idx]

    def aggregate_to_level(self, region_lengths: Dict[str, float],
                           target_level: int, strip_prefixes: bool = False) -> Tuple[Dict[str, float], List[str]]:
        """
        Aggregate region lengths to target hierarchy level using index-based lookup.

        Args:
            region_lengths: Dict of {region_name_or_index: length}
            target_level: Target hierarchy level (1-6)

        Returns:
            Aggregated dict of {parent_region: total_length}
        """
        result = {}
        unmapped = []

        for region_key, length in region_lengths.items():
            target = self.get_at_level(region_key, target_level)
            if target is None:
                unmapped.append(region_key)
                continue
            if strip_prefixes:
                target = self._strip_prefix(target)
            result[target] = result.get(target, 0) + length

        return result, unmapped

    @classmethod
    def load_file(cls, path: Union[str, Path], name: str = "") -> "HierarchyTable":
        """Load hierarchy from CSV file."""
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Hierarchy file not found: {path}")

        if path.suffix.lower() in {".xlsx", ".xls"}:
            return cls(pd.read_excel(path), name=name or path.stem)

        try:
            # Try different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(path, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                df = pd.read_csv(path, encoding='utf-8', errors='replace')

            if name == "":
                name = path.stem

            return cls(df, name=name)

        except Exception:
            raise


class DualHierarchyTable:
    """
    Combines cortical (CHARM) and subcortical (SARM) hierarchy tables.
    Routes lookups based on region prefix:
    - CL_*, CR_* -> cortical
    - SL_*, SR_* -> subcortical
    """

    def __init__(self, cortex: HierarchyTable = None, subcortex: HierarchyTable = None,
                 cortex_paths: List[Union[str, Path]] = None,
                 subcortical_paths: List[Union[str, Path]] = None):
        """
        Initialize dual hierarchy.

        Args:
            cortex: Pre-loaded HierarchyTable for cortex
            subcortex: Pre-loaded HierarchyTable for subcortex
            cortex_paths: Path(s) to cortical hierarchy CSV file(s)
            subcortical_paths: Path(s) to subcortical hierarchy CSV file(s)
        """
        # Load from paths if provided
        if cortex_paths:
            if isinstance(cortex_paths, (str, Path)):
                cortex_paths = [cortex_paths]
            cortex = HierarchyTable.load_file(cortex_paths[0], name="cortex")

        if subcortical_paths:
            if isinstance(subcortical_paths, (str, Path)):
                subcortical_paths = [subcortical_paths]
            subcortex = HierarchyTable.load_file(subcortical_paths[0], name="subcortex")

        self.cortex = cortex
        self.subcortex = subcortex

    def _get_table(self, region: str) -> Optional[HierarchyTable]:
        """Get appropriate table based on region prefix or index."""
        region = str(region).strip()

        if region.startswith(('CL_', 'CR_')):
            return self.cortex
        elif region.startswith(('SL_', 'SR_')):
            return self.subcortex
        else:
            # Try numeric index lookup
            try:
                idx = int(region)
                # Subcortical indices are typically >= 1000 (ARM convention)
                if idx >= 1000 and self.subcortex and idx in self.subcortex.index_paths:
                    return self.subcortex
                if idx < 1000 and self.cortex and idx in self.cortex.index_paths:
                    return self.cortex
                # Fallback: try both
                if self.subcortex and idx in self.subcortex.index_paths:
                    return self.subcortex
                if self.cortex and idx in self.cortex.index_paths:
                    return self.cortex
            except ValueError:
                pass

            # Try both tables by name
            if self.cortex and region in self.cortex.region_paths:
                return self.cortex
            if self.subcortex and region in self.subcortex.region_paths:
                return self.subcortex

            return self.cortex or self.subcortex

    def get_path(self, region: str) -> Optional[List[str]]:
        """Get hierarchy path for a region."""
        table = self._get_table(region)
        return table.get_path(region) if table else None

    def get_at_level(self, region: str, level: int) -> Optional[str]:
        """Get region at specified hierarchy level."""
        table = self._get_table(region)
        return table.get_at_level(region, level) if table else None

    def lookup_by_index(self, index: int, level: int = None) -> Optional[Union[str, List[str]]]:
        """Lookup by numeric index - try subcortex first (indices >= 1000), then cortex."""
        # Try subcortex first for high indices (>= 1000 typically subcortical)
        if self.subcortex:
            result = self.subcortex.lookup_by_index(index, level)
            if result:
                return result

        # Try cortex
        if self.cortex:
            result = self.cortex.lookup_by_index(index, level)
            if result:
                return result

        return None

    def aggregate_to_level(self, region_lengths: Dict[str, float],
                           target_level: int,
                           strip_prefixes: bool = False) -> Tuple[Dict[str, float], List[str]]:
        """
        Aggregate region lengths to target level, routing to appropriate table.

        Args:
            region_lengths: Dict of {region_name_or_index: length}
            target_level: Target hierarchy level
            strip_prefixes: If True, remove CL_/CR_/SL_/SR_ prefixes from result keys

        Returns:
            Tuple of (aggregated_dict, unmapped_regions)
        """
        result = {}
        unmapped = []

        for region_key, length in region_lengths.items():
            # Get appropriate table
            table = self._get_table(region_key)

            if table is None:
                unmapped.append(region_key)
                continue

            # Try lookup
            target = table.get_at_level(region_key, target_level)

            if target is not None:
                # Strip prefix if requested
                if strip_prefixes:
                    target = HierarchyTable._strip_prefix(target)
                result[target] = result.get(target, 0) + length
            else:
                # Try numeric index
                try:
                    idx = int(region_key)
                    target = self.lookup_by_index(idx, target_level)
                    if target:
                        # Strip prefix if requested
                        if strip_prefixes:
                            target = HierarchyTable._strip_prefix(target)
                        result[target] = result.get(target, 0) + length
                    else:
                        unmapped.append(region_key)
                except ValueError:
                    unmapped.append(region_key)

        return result, unmapped
