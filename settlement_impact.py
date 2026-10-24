"""
Settlement Impact Assessment Module for Guardian of the Terai

This module calculates the impact of flood extents on settlements and roads
in the Saptari-Sunsari region of Nepal.

Author: Settlement Impact Assessment Team
Date: 2026-10-22
"""

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, mapping
from shapely.validation import make_valid
import os
import logging
from pathlib import Path
from typing import Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def validate_and_fix_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Validate and fix invalid geometries in a GeoDataFrame.
    
    Args:
        gdf: Input GeoDataFrame
        
    Returns:
        GeoDataFrame with valid geometries
    """
    original_count = len(gdf)
    
    # Check for invalid geometries
    invalid_mask = ~gdf.geometry.is_valid
    invalid_count = invalid_mask.sum()
    
    if invalid_count > 0:
        logger.warning(f"Found {invalid_count} invalid geometries out of {original_count}")
        
        # Fix invalid geometries
        gdf.loc[invalid_mask, 'geometry'] = gdf.loc[invalid_mask, 'geometry'].apply(
            lambda geom: make_valid(geom) if not geom.is_valid else geom
        )
        
        # Remove null geometries that may result from fixing
        gdf = gdf[gdf.geometry.notna()]
        
        logger.info(f"Fixed {invalid_count} geometries, {len(gdf)} valid geometries remain")
    
    return gdf


def ensure_crs_compatibility(gdf1: gpd.GeoDataFrame, gdf2: gpd.GeoDataFrame) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Ensure two GeoDataFrames have compatible CRS. If different, reproject to a common CRS.
    
    Args:
        gdf1: First GeoDataFrame
        gdf2: Second GeoDataFrame
        
    Returns:
        Tuple of reprojected GeoDataFrames
    """
    if gdf1.crs is None:
        logger.warning("gdf1 has no CRS, assuming EPSG:4326")
        gdf1 = gdf1.set_crs(epsg=4326)
    
    if gdf2.crs is None:
        logger.warning("gdf2 has no CRS, assuming EPSG:4326")
        gdf2 = gdf2.set_crs(epsg=4326)
    
    if gdf1.crs != gdf2.crs:
        logger.info(f"CRS mismatch: {gdf1.crs} vs {gdf2.crs}. Reprojecting to {gdf1.crs}")
        gdf2 = gdf2.to_crs(gdf1.crs)
    
    return gdf1, gdf2


def reproject_to_area_calculation(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Reproject GeoDataFrame to an appropriate projected CRS for area/length calculations.
    For Nepal, UTM zone 45N (EPSG:32645) is suitable.
    
    Args:
        gdf: Input GeoDataFrame (should be in WGS84)
        
    Returns:
        GeoDataFrame in projected CRS
    """
    # UTM zone 45N covers Nepal
    projected_crs = "EPSG:32645"
    
    if gdf.crs != projected_crs:
        logger.info(f"Reprojecting to {projected_crs} for area/length calculations")
        gdf = gdf.to_crs(projected_crs)
    
    return gdf


def calculate_settlement_impact(
    flood_gdf: gpd.GeoDataFrame,
    settlements_gdf: gpd.GeoDataFrame,
    roads_gdf: Optional[gpd.GeoDataFrame] = None
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Calculate the impact of flood on settlements and roads.
    
    Args:
        flood_gdf: GeoDataFrame containing flood extent (polygon)
        settlements_gdf: GeoDataFrame containing settlements (points or polygons)
        roads_gdf: Optional GeoDataFrame containing roads (lines)
        
    Returns:
        Tuple of (settlement_impact_gdf, road_impact_gdf)
    """
    logger.info("Calculating settlement impact...")
    
    # Validate geometries
    flood_gdf = validate_and_fix_geometries(flood_gdf)
    settlements_gdf = validate_and_fix_geometries(settlements_gdf)
    
    # Ensure CRS compatibility
    flood_gdf, settlements_gdf = ensure_crs_compatibility(flood_gdf, settlements_gdf)
    
    # Handle different settlement geometry types
    settlement_points = settlements_gdf[settlements_gdf.geometry.type == 'Point']
    settlement_polygons = settlements_gdf[settlements_gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
    
    # Reproject to projected CRS for accurate area calculations
    flood_projected = reproject_to_area_calculation(flood_gdf)
    settlement_polygons_projected = reproject_to_area_calculation(settlement_polygons)
    
    # Calculate intersection for polygon settlements
    if len(settlement_polygons_projected) > 0:
        # Use inner join to avoid column duplication issues
        settlement_impact = gpd.sjoin(settlement_polygons_projected, flood_projected, how='left', predicate='intersects')
        
        # Calculate flooded area for each settlement
        settlement_impact['flooded_area_sqm'] = 0.0
        settlement_impact['total_area_sqm'] = settlement_impact.geometry.area
        settlement_impact['flooded_percentage'] = 0.0
        
        for idx, row in settlement_impact.iterrows():
            if pd.notna(row['index_right']):  # Intersects with flood
                try:
                    flood_idx = int(row['index_right'])
                    flood_geom = flood_projected.geometry.iloc[flood_idx]
                    intersection = row.geometry.intersection(flood_geom)
                    if not intersection.is_empty:
                        settlement_impact.at[idx, 'flooded_area_sqm'] = intersection.area
                        settlement_impact.at[idx, 'flooded_percentage'] = (intersection.area / row.geometry.area) * 100
                except (ValueError, IndexError, KeyError) as e:
                    logger.warning(f"Could not calculate intersection for settlement {idx}: {e}")
    else:
        settlement_impact = settlement_polygons.copy()
        settlement_impact['flooded_area_sqm'] = 0.0
        settlement_impact['total_area_sqm'] = 0.0
        settlement_impact['flooded_percentage'] = 0.0
    
    # Handle point settlements - just mark as flooded or not
    if len(settlement_points) > 0:
        flood_gdf, settlement_points = ensure_crs_compatibility(flood_gdf, settlement_points)
        point_impact = gpd.sjoin(settlement_points, flood_gdf, how='left', predicate='intersects')
        point_impact['flooded_area_sqm'] = 0.0
        point_impact['total_area_sqm'] = 0.0
        point_impact['flooded_percentage'] = point_impact['index_right'].apply(lambda x: 100 if pd.notna(x) else 0)
        
        # Clean up point impact
        if 'index_right' in point_impact.columns:
            point_impact = point_impact.drop(columns=['index_right'])
        
        # Combine polygon and point results
        settlement_impact = pd.concat([settlement_impact, point_impact], ignore_index=True)
    
    # Clean up the result - remove spatial join artifacts
    if 'index_flood' in settlement_impact.columns:
        settlement_impact = settlement_impact.drop(columns=['index_flood'])
    
    # Clean up the result - remove spatial join artifacts
    if 'index_right' in settlement_impact.columns:
        settlement_impact = settlement_impact.drop(columns=['index_right'])
    
    # Drop columns with _left or _right suffixes (from spatial join)
    columns_to_drop = [col for col in settlement_impact.columns if col.endswith('_left') or col.endswith('_right')]
    if columns_to_drop:
        settlement_impact = settlement_impact.drop(columns=columns_to_drop)
    
    # Drop any flood metadata columns that got merged (check for test data markers)
    for col in ['description', 'date', 'source']:
        if col in settlement_impact.columns:
            # Only drop if it looks like it came from the flood layer
            if settlement_impact[col].astype(str).str.contains('SYNTHETIC|test', na=False).any():
                settlement_impact = settlement_impact.drop(columns=[col])
    
    # Add is_flooded flag
    settlement_impact['is_flooded'] = settlement_impact['flooded_percentage'] > 0
    
    # Calculate road impact if provided
    road_impact = None
    if roads_gdf is not None and len(roads_gdf) > 0:
        logger.info("Calculating road impact...")
        roads_gdf = validate_and_fix_geometries(roads_gdf)
        flood_gdf, roads_gdf = ensure_crs_compatibility(flood_gdf, roads_gdf)
        
        # Reproject for length calculations
        roads_projected = reproject_to_area_calculation(roads_gdf)
        
        # Find roads intersecting flood
        road_impact = gpd.sjoin(roads_projected, flood_projected, how='left', predicate='intersects')
        
        # Calculate affected road length
        road_impact['total_length_m'] = road_impact.geometry.length
        road_impact['flooded_length_m'] = 0.0
        road_impact['flooded_percentage'] = 0.0
        
        for idx, row in road_impact.iterrows():
            if pd.notna(row['index_right']):  # Intersects with flood
                try:
                    flood_idx = int(row['index_right'])
                    flood_geom = flood_projected.geometry.iloc[flood_idx]
                    intersection = row.geometry.intersection(flood_geom)
                    if not intersection.is_empty:
                        road_impact.at[idx, 'flooded_length_m'] = intersection.length
                        road_impact.at[idx, 'flooded_percentage'] = (intersection.length / row.geometry.length) * 100
                except (ValueError, IndexError, KeyError) as e:
                    logger.warning(f"Could not calculate intersection for road {idx}: {e}")
        
        # Clean up
        if 'index_right' in road_impact.columns:
            road_impact = road_impact.drop(columns=['index_right'])
        
        # Drop columns with _left or _right suffixes (from spatial join)
        columns_to_drop = [col for col in road_impact.columns if col.endswith('_left') or col.endswith('_right')]
        if columns_to_drop:
            road_impact = road_impact.drop(columns=columns_to_drop)
        
        # Drop any flood metadata columns that got merged
        for col in ['description', 'date', 'source']:
            if col in road_impact.columns:
                road_impact = road_impact.drop(columns=[col])
        
        road_impact['is_flooded'] = road_impact['flooded_percentage'] > 0
    
    return settlement_impact, road_impact


def calculate_priority_ranking(settlement_impact: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Assign priority ranking to settlements based on flood impact.
    
    Priority levels:
    - Critical: > 50% flooded
    - High: 25-50% flooded
    - Medium: 10-25% flooded
    - Low: 1-10% flooded
    - None: 0% flooded
    
    Args:
        settlement_impact: GeoDataFrame with flood impact metrics
        
    Returns:
        GeoDataFrame with priority column added
    """
    def assign_priority(row):
        flood_pct = row['flooded_percentage']
        if pd.isna(flood_pct) or flood_pct == 0:
            return 'None'
        elif flood_pct >= 50:
            return 'Critical'
        elif flood_pct >= 25:
            return 'High'
        elif flood_pct >= 10:
            return 'Medium'
        elif flood_pct >= 1:
            return 'Low'
        else:
            return 'None'
    
    settlement_impact['priority'] = settlement_impact.apply(assign_priority, axis=1)
    
    # Ensure no NaN values in priority
    settlement_impact['priority'] = settlement_impact['priority'].fillna('None')
    
    logger.info(f"Priority distribution:\n{settlement_impact['priority'].value_counts()}")
    
    return settlement_impact


def analyze_impact(
    flood_geojson: str,
    settlements_file: str,
    roads_file: Optional[str] = None,
    output_dir: str = "data/vector/impact"
) -> Tuple[str, str]:
    """
    Main function to analyze flood impact on settlements and roads.
    
    Args:
        flood_geojson: Path to flood extent GeoJSON file
        settlements_file: Path to settlements GeoJSON file
        roads_file: Optional path to roads GeoJSON file
        output_dir: Directory to save output files
        
    Returns:
        Tuple of (output_csv_path, output_geojson_path)
    """
    logger.info(f"Starting settlement impact analysis...")
    logger.info(f"Flood extent: {flood_geojson}")
    logger.info(f"Settlements: {settlements_file}")
    if roads_file:
        logger.info(f"Roads: {roads_file}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Load data
    try:
        flood_gdf = gpd.read_file(flood_geojson)
        logger.info(f"Loaded flood extent: {len(flood_gdf)} features, CRS: {flood_gdf.crs}")
    except Exception as e:
        logger.error(f"Failed to load flood extent: {e}")
        raise
    
    try:
        settlements_gdf = gpd.read_file(settlements_file)
        logger.info(f"Loaded settlements: {len(settlements_gdf)} features, CRS: {settlements_gdf.crs}")
    except Exception as e:
        logger.error(f"Failed to load settlements: {e}")
        raise
    
    roads_gdf = None
    if roads_file:
        try:
            roads_gdf = gpd.read_file(roads_file)
            logger.info(f"Loaded roads: {len(roads_gdf)} features, CRS: {roads_gdf.crs}")
        except Exception as e:
            logger.warning(f"Failed to load roads: {e}. Continuing without road analysis.")
    
    # Calculate impact
    settlement_impact, road_impact = calculate_settlement_impact(flood_gdf, settlements_gdf, roads_gdf)
    
    # Add priority ranking
    settlement_impact = calculate_priority_ranking(settlement_impact)
    
    # Reproject back to WGS84 for output
    if settlement_impact.crs != "EPSG:4326":
        settlement_impact = settlement_impact.to_crs(epsg=4326)
    
    # Save outputs
    output_csv = os.path.join(output_dir, "settlement_impact.csv")
    output_geojson = os.path.join(output_dir, "settlement_impact.geojson")
    
    # Save CSV (drop geometry column)
    settlement_impact_no_geom = settlement_impact.drop(columns=['geometry'])
    settlement_impact_no_geom.to_csv(output_csv, index=False)
    logger.info(f"Saved settlement impact CSV: {output_csv}")
    
    # Save GeoJSON
    settlement_impact.to_file(output_geojson, driver='GeoJSON')
    logger.info(f"Saved settlement impact GeoJSON: {output_geojson}")
    
    # Save road impact if available
    if road_impact is not None:
        road_output_csv = os.path.join(output_dir, "road_impact.csv")
        road_output_geojson = os.path.join(output_dir, "road_impact.geojson")
        
        road_impact_no_geom = road_impact.drop(columns=['geometry'])
        road_impact_no_geom.to_csv(road_output_csv, index=False)
        logger.info(f"Saved road impact CSV: {road_output_csv}")
        
        if road_impact.crs != "EPSG:4326":
            road_impact = road_impact.to_crs(epsg=4326)
        road_impact.to_file(road_output_geojson, driver='GeoJSON')
        logger.info(f"Saved road impact GeoJSON: {road_output_geojson}")
    
    # Print summary
    flooded_count = (settlement_impact['is_flooded']).sum()
    total_count = len(settlement_impact)
    logger.info(f"\n=== Impact Summary ===")
    logger.info(f"Total settlements: {total_count}")
    logger.info(f"Flooded settlements: {flooded_count} ({flooded_count/total_count*100:.1f}%)")
    logger.info(f"Critical priority: {(settlement_impact['priority'] == 'Critical').sum()}")
    logger.info(f"High priority: {(settlement_impact['priority'] == 'High').sum()}")
    
    if road_impact is not None:
        flooded_roads = (road_impact['is_flooded']).sum()
        total_roads = len(road_impact)
        logger.info(f"Total roads: {total_roads}")
        logger.info(f"Flooded roads: {flooded_roads} ({flooded_roads/total_roads*100:.1f}%)")
    
    return output_csv, output_geojson


def create_test_flood_polygon(output_path: str = "data/vector/test_flood.geojson"):
    """
    Create a synthetic test flood polygon in the Saptari-Sunsari region.
    This is for testing purposes only and is labeled as test data.
    
    Args:
        output_path: Path to save the test flood polygon
    """
    logger.info("Creating synthetic test flood polygon (for testing only)")
    
    # Create a polygon in the study area (approximate coordinates)
    # This is TEST DATA, not a real flood extent
    # Sized to cover some settlements for testing
    test_coords = [
        [86.88, 26.54],
        [86.96, 26.54],
        [86.96, 26.61],
        [86.88, 26.61],
        [86.88, 26.54]
    ]
    
    flood_polygon = Polygon(test_coords)
    
    # Create GeoDataFrame
    flood_gdf = gpd.GeoDataFrame(
        {
            'name': ['Test Flood Polygon'],
            'description': ['SYNTHETIC TEST DATA - Not a real flood extent'],
            'date': ['2026-10-22'],
            'source': ['synthetic_test']
        },
        geometry=[flood_polygon],
        crs="EPSG:4326"
    )
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    flood_gdf.to_file(output_path, driver='GeoJSON')
    logger.info(f"Saved test flood polygon: {output_path}")
    
    return output_path


if __name__ == "__main__":
    # Example usage with test data
    logger.info("=== Settlement Impact Assessment Module ===")
    logger.info("This module calculates flood impact on settlements and roads")
    
    # Create test flood polygon
    test_flood_path = create_test_flood_polygon()
    
    # Note: This requires OSM settlement and road data to be downloaded first
    # The actual paths will depend on where the OSM data is extracted
    logger.info("\nTo run a full analysis:")
    logger.info("1. Download OSM data for Nepal or extract from larger dataset")
    logger.info("2. Extract settlements and roads clipped to study area")
    logger.info("3. Run: python settlement_impact.py")
    logger.info("\nOr call analyze_impact() with your data paths:")
    logger.info("analyze_impact('flood_extent.geojson', 'settlements.geojson', 'roads.geojson')")
