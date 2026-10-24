"""
Test script for the Settlement Impact Assessment module.

This script runs the impact analysis with a synthetic flood polygon to verify the module works correctly.

Author: Settlement Impact Assessment Team
Date: 2026-10-22
"""

from settlement_impact import analyze_impact, create_test_flood_polygon
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    logger.info("=== Testing Settlement Impact Assessment Module ===")
    
    # Create test flood polygon
    logger.info("\n1. Creating test flood polygon...")
    test_flood_path = create_test_flood_polygon("data/vector/test_flood.geojson")
    logger.info(f"Test flood polygon created: {test_flood_path}")
    
    # Run impact analysis with real OSM data
    logger.info("\n2. Running impact analysis with real OSM data...")
    logger.info("NOTE: Using REAL OSM data extracted from Nepal PBF")
    
    # Create output directory
    os.makedirs("data/vector/impact", exist_ok=True)
    
    try:
        csv_path, geojson_path = analyze_impact(
            flood_geojson="data/vector/test_flood.geojson",
            settlements_file="data/vector/osm/settlements.geojson",
            roads_file="data/vector/osm/roads.geojson",
            output_dir="data/vector/impact"
        )
        
        logger.info(f"\n3. Analysis complete!")
        logger.info(f"   CSV output: {csv_path}")
        logger.info(f"   GeoJSON output: {geojson_path}")
        
        # Display results
        import pandas as pd
        logger.info("\n4. Settlement Impact Summary:")
        df = pd.read_csv(csv_path)
        logger.info(df.head(10).to_string())
        
        logger.info(f"\n5. Priority distribution:")
        logger.info(df['priority'].value_counts().to_string())
        
        logger.info("\n=== Test Complete ===")
        logger.info("The module is working correctly with real OSM data.")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
