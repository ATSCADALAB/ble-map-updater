"""
Map Data Validation

Validates:
- GeoJSON FeatureCollection structure
- Zone geometry validity
- Speed limit requirements
- Required metadata attributes
- Coordinate system compliance
"""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass

class MapValidator:
    """
    Validates map data according to Cycle Sentinel requirements
    
    Requirements from specification:
    - GeoJSON FeatureCollection format
    - Valid zone geometries (Polygon/MultiPolygon)
    - Speed limits ≥ 15km/h (unless explicitly marked pedestrian-only)
    - Required metadata attributes
    - Coordinate bounds validation
    """
    
    def __init__(self):
        # Validation constraints
        self.min_speed_limit = 15  # km/h
        self.max_speed_limit = 100  # km/h
        
        # Coordinate bounds (adjust for your region)
        # Example: Vietnam bounds
        self.coordinate_bounds = {
            "lat_min": 8.0,   # Southern Vietnam
            "lat_max": 24.0,  # Northern Vietnam  
            "lon_min": 102.0, # Western Vietnam
            "lon_max": 110.0  # Eastern Vietnam
        }
        
        # Required zone types
        self.valid_zone_types = {
            "school", "hospital", "residential", "commercial", 
            "industrial", "park", "restricted", "highway", "pedestrian"
        }
        
    def validate_map_structure(self, map_data: Dict[str, Any]) -> bool:
        """
        Comprehensive map structure validation
        
        Args:
            map_data: Map data to validate
            
        Returns:
            bool: True if valid
            
        Raises:
            ValidationError: If validation fails
        """
        
        try:
            # 1. Root structure validation
            self._validate_root_structure(map_data)
            
            # 2. Metadata validation
            self._validate_metadata(map_data.get("metadata", {}))
            
            # 3. Features validation
            self._validate_features(map_data.get("features", []))
            
            # 4. Cross-feature validation
            self._validate_cross_features(map_data.get("features", []))
            
            return True
            
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Unexpected validation error: {e}")
    
    def _validate_root_structure(self, map_data: Dict[str, Any]):
        """Validate GeoJSON FeatureCollection root structure"""
        
        # Check type
        if map_data.get("type") != "FeatureCollection":
            raise ValidationError(
                f"Invalid root type: expected 'FeatureCollection', got '{map_data.get('type')}'"
            )
        
        # Check required fields
        required_fields = ["type", "features"]
        for field in required_fields:
            if field not in map_data:
                raise ValidationError(f"Missing required field: '{field}'")
        
        # Check features is list
        if not isinstance(map_data["features"], list):
            raise ValidationError("Features must be a list")
        
        if len(map_data["features"]) == 0:
            raise ValidationError("Map must contain at least one feature")
    
    def _validate_metadata(self, metadata: Dict[str, Any]):
        """Validate map metadata"""
        
        # Required metadata fields
        required_fields = ["version", "created"]
        for field in required_fields:
            if field not in metadata:
                raise ValidationError(f"Missing required metadata field: '{field}'")
        
        # Version validation
        version = metadata["version"]
        if not isinstance(version, int) or version <= 0:
            raise ValidationError(f"Invalid version: must be positive integer, got {version}")
        
        # Date format validation (ISO 8601)
        created = metadata["created"]
        if not self._validate_iso_date(created):
            raise ValidationError(f"Invalid created date format: {created}")
        
        # Optional field validation
        if "authority" in metadata:
            if not isinstance(metadata["authority"], str) or len(metadata["authority"]) < 1:
                raise ValidationError("Authority must be non-empty string")
    
    def _validate_features(self, features: List[Dict[str, Any]]):
        """Validate all map features"""
        
        for i, feature in enumerate(features):
            try:
                self._validate_single_feature(feature)
            except ValidationError as e:
                raise ValidationError(f"Feature {i}: {e}")
    
    def _validate_single_feature(self, feature: Dict[str, Any]):
        """Validate individual feature"""
        
        # 1. Feature structure
        if feature.get("type") != "Feature":
            raise ValidationError(f"Invalid feature type: {feature.get('type')}")
        
        required_fields = ["type", "properties", "geometry"]
        for field in required_fields:
            if field not in feature:
                raise ValidationError(f"Missing required field: '{field}'")
        
        # 2. Geometry validation
        self._validate_geometry(feature["geometry"])
        
        # 3. Properties validation
        self._validate_properties(feature["properties"])
    
    def _validate_geometry(self, geometry: Dict[str, Any]):
        """Validate feature geometry"""
        
        # Check geometry type
        geom_type = geometry.get("type")
        if geom_type not in ["Polygon", "MultiPolygon"]:
            raise ValidationError(
                f"Invalid geometry type: {geom_type}. Only Polygon and MultiPolygon supported"
            )
        
        # Check coordinates
        coordinates = geometry.get("coordinates")
        if not coordinates:
            raise ValidationError("Missing geometry coordinates")
        
        # Validate coordinate structure
        if geom_type == "Polygon":
            self._validate_polygon_coordinates(coordinates)
        elif geom_type == "MultiPolygon":
            if not isinstance(coordinates, list):
                raise ValidationError("MultiPolygon coordinates must be array")
            
            for i, polygon_coords in enumerate(coordinates):
                try:
                    self._validate_polygon_coordinates(polygon_coords)
                except ValidationError as e:
                    raise ValidationError(f"MultiPolygon polygon {i}: {e}")
    
    def _validate_polygon_coordinates(self, coordinates: List):
        """Validate polygon coordinate structure"""
        
        if not isinstance(coordinates, list) or len(coordinates) == 0:
            raise ValidationError("Polygon coordinates must be non-empty array")
        
        # Each polygon is array of linear rings
        for i, ring in enumerate(coordinates):
            if not isinstance(ring, list):
                raise ValidationError(f"Ring {i} must be array")
            
            if len(ring) < 4:
                raise ValidationError(f"Ring {i} must have at least 4 coordinates")
            
            # Validate individual coordinates
            for j, coord in enumerate(ring):
                self._validate_coordinate(coord, f"Ring {i}, coordinate {j}")
            
            # Check if ring is closed
            if ring[0] != ring[-1]:
                raise ValidationError(f"Ring {i} must be closed (first and last coordinates equal)")
    
    def _validate_coordinate(self, coord: List, context: str = ""):
        """Validate individual coordinate [lon, lat]"""
        
        if not isinstance(coord, list) or len(coord) != 2:
            raise ValidationError(f"{context}: Coordinate must be [longitude, latitude] array")
        
        lon, lat = coord
        
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            raise ValidationError(f"{context}: Coordinates must be numeric")
        
        # Validate longitude range
        if not (-180 <= lon <= 180):
            raise ValidationError(f"{context}: Longitude {lon} out of range [-180, 180]")
        
        # Validate latitude range
        if not (-90 <= lat <= 90):
            raise ValidationError(f"{context}: Latitude {lat} out of range [-90, 90]")
        
        # Validate coordinate bounds (region-specific)
        if not (self.coordinate_bounds["lon_min"] <= lon <= self.coordinate_bounds["lon_max"]):
            raise ValidationError(
                f"{context}: Longitude {lon} outside expected region bounds "
                f"[{self.coordinate_bounds['lon_min']}, {self.coordinate_bounds['lon_max']}]"
            )
        
        if not (self.coordinate_bounds["lat_min"] <= lat <= self.coordinate_bounds["lat_max"]):
            raise ValidationError(
                f"{context}: Latitude {lat} outside expected region bounds "
                f"[{self.coordinate_bounds['lat_min']}, {self.coordinate_bounds['lat_max']}]"
            )
    
    def _validate_properties(self, properties: Dict[str, Any]):
        """Validate feature properties"""
        
        # Required properties
        required_props = ["zone_name", "zone_type", "speed_limit"]
        for prop in required_props:
            if prop not in properties:
                raise ValidationError(f"Missing required property: '{prop}'")
        
        # Zone name validation
        zone_name = properties["zone_name"]
        if not isinstance(zone_name, str) or len(zone_name.strip()) == 0:
            raise ValidationError("zone_name must be non-empty string")
        
        # Zone type validation
        zone_type = properties["zone_type"]
        if zone_type not in self.valid_zone_types:
            raise ValidationError(
                f"Invalid zone_type: '{zone_type}'. "
                f"Valid types: {sorted(self.valid_zone_types)}"
            )
        
        # Speed limit validation
        speed_limit = properties["speed_limit"]
        if not isinstance(speed_limit, (int, float)):
            raise ValidationError("speed_limit must be numeric")
        
        # Special case: pedestrian zones can have speed_limit = 0
        if zone_type == "pedestrian":
            if speed_limit != 0:
                raise ValidationError("Pedestrian zones must have speed_limit = 0")
        else:
            if speed_limit < self.min_speed_limit:
                raise ValidationError(
                    f"Speed limit {speed_limit} below minimum {self.min_speed_limit} km/h "
                    f"for non-pedestrian zone"
                )
        
        if speed_limit > self.max_speed_limit:
            raise ValidationError(f"Speed limit {speed_limit} exceeds maximum {self.max_speed_limit} km/h")
        
        # Optional properties validation
        if "description" in properties:
            if not isinstance(properties["description"], str):
                raise ValidationError("description must be string")
        
        if "enforcement_hours" in properties:
            hours = properties["enforcement_hours"]
            if not isinstance(hours, str) or not self._validate_time_format(hours):
                raise ValidationError(f"Invalid enforcement_hours format: {hours}")
    
    def _validate_cross_features(self, features: List[Dict[str, Any]]):
        """Validate relationships between features"""
        
        # Check for duplicate zone names
        zone_names = []
        for feature in features:
            zone_name = feature["properties"]["zone_name"]
            if zone_name in zone_names:
               raise ValidationError(f"Duplicate zone name: '{zone_name}'")
           zone_names.append(zone_name)
       
       # Check for overlapping geometries with conflicting rules
       self._check_geometry_conflicts(features)
   
   def _check_geometry_conflicts(self, features: List[Dict[str, Any]]):
       """Check for conflicting overlapping zones"""
       
       # Simple overlap detection (can be enhanced with proper geometric intersection)
       for i, feature1 in enumerate(features):
           for j, feature2 in enumerate(features[i+1:], i+1):
               # Check if zones have conflicting speed limits
               speed1 = feature1["properties"]["speed_limit"]
               speed2 = feature2["properties"]["speed_limit"]
               
               # If speed limits differ significantly, warn about potential conflicts
               if abs(speed1 - speed2) > 10:  # 10 km/h difference
                   zone1 = feature1["properties"]["zone_name"]
                   zone2 = feature2["properties"]["zone_name"]
                   
                   # For now, just log warning (could be enhanced to detect actual overlaps)
                   print(f"⚠️  Potential conflict between '{zone1}' ({speed1} km/h) "
                         f"and '{zone2}' ({speed2} km/h)")
   
   def _validate_iso_date(self, date_string: str) -> bool:
       """Validate ISO 8601 date format"""
       
       # Simple regex for ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ
       iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$'
       return bool(re.match(iso_pattern, date_string))
   
   def _validate_time_format(self, time_string: str) -> bool:
       """Validate time format for enforcement hours"""
       
       # Accept formats like "08:00-18:00", "24/7", "weekdays 09:00-17:00"
       patterns = [
           r'^\d{2}:\d{2}-\d{2}:\d{2}$',  # 08:00-18:00
           r'^24/7$',                      # 24/7
           r'^weekdays \d{2}:\d{2}-\d{2}:\d{2}$',  # weekdays 09:00-17:00
           r'^weekends \d{2}:\d{2}-\d{2}:\d{2}$'   # weekends 10:00-16:00
       ]
       
       return any(re.match(pattern, time_string) for pattern in patterns)
   
   def validate_map_file(self, file_path: str) -> Dict[str, Any]:
       """
       Validate map file and return validation report
       
       Args:
           file_path: Path to map file
           
       Returns:
           Dict: Validation report with status and details
       """
       
       validation_report = {
           "valid": False,
           "file_path": file_path,
           "file_size": 0,
           "features_count": 0,
           "errors": [],
           "warnings": [],
           "metadata": {}
       }
       
       try:
           # Check file exists
           path = Path(file_path)
           if not path.exists():
               validation_report["errors"].append(f"File does not exist: {file_path}")
               return validation_report
           
           validation_report["file_size"] = path.stat().st_size
           
           # Load and parse JSON
           try:
               with open(path, 'r', encoding='utf-8') as f:
                   map_data = json.load(f)
           except json.JSONDecodeError as e:
               validation_report["errors"].append(f"Invalid JSON: {e}")
               return validation_report
           except UnicodeDecodeError as e:
               validation_report["errors"].append(f"Invalid encoding: {e}")
               return validation_report
           
           # Extract basic info
           validation_report["features_count"] = len(map_data.get("features", []))
           validation_report["metadata"] = map_data.get("metadata", {})
           
           # Perform validation
           self.validate_map_structure(map_data)
           
           # If we get here, validation passed
           validation_report["valid"] = True
           validation_report["message"] = "Map validation successful"
           
       except ValidationError as e:
           validation_report["errors"].append(str(e))
       except Exception as e:
           validation_report["errors"].append(f"Unexpected error: {e}")
       
       return validation_report

def create_sample_map() -> Dict[str, Any]:
   """Create a sample valid map for testing"""
   
   return {
       "type": "FeatureCollection",
       "metadata": {
           "version": 1,
           "created": "2025-06-27T15:30:00Z",
           "authority": "Ho Chi Minh City Transport Department",
           "description": "Sample speed zones for District 1"
       },
       "features": [
           {
               "type": "Feature",
               "properties": {
                   "zone_name": "Nguyen Hue Pedestrian Street",
                   "zone_type": "pedestrian",
                   "speed_limit": 0,
                   "description": "Pedestrian-only zone",
                   "enforcement_hours": "24/7"
               },
               "geometry": {
                   "type": "Polygon",
                   "coordinates": [[
                       [106.7011, 10.7742],
                       [106.7015, 10.7742],
                       [106.7015, 10.7748],
                       [106.7011, 10.7748],
                       [106.7011, 10.7742]
                   ]]
               }
           },
           {
               "type": "Feature", 
               "properties": {
                   "zone_name": "District 1 School Zone",
                   "zone_type": "school",
                   "speed_limit": 20,
                   "description": "Reduced speed near schools",
                   "enforcement_hours": "weekdays 07:00-18:00"
               },
               "geometry": {
                   "type": "Polygon",
                   "coordinates": [[
                       [106.6950, 10.7700],
                       [106.7050, 10.7700],
                       [106.7050, 10.7800],
                       [106.6950, 10.7800],
                       [106.6950, 10.7700]
                   ]]
               }
           },
           {
               "type": "Feature",
               "properties": {
                   "zone_name": "Residential Area",
                   "zone_type": "residential", 
                   "speed_limit": 25,
                   "description": "Standard residential speed limit"
               },
               "geometry": {
                   "type": "Polygon",
                   "coordinates": [[
                       [106.6800, 10.7600],
                       [106.6900, 10.7600],
                       [106.6900, 10.7700],
                       [106.6800, 10.7700],
                       [106.6800, 10.7600]
                   ]]
               }
           }
       ]
   }

# Testing function
def test_validator():
   """Test the validator with sample data"""
   
   print("🧪 Testing Map Validator")
   print("=" * 30)
   
   validator = MapValidator()
   
   # Test 1: Valid map
   print("1️⃣ Testing valid map...")
   try:
       sample_map = create_sample_map()
       validator.validate_map_structure(sample_map)
       print("   ✅ Valid map passed validation")
   except ValidationError as e:
       print(f"   ❌ Valid map failed: {e}")
   
   # Test 2: Invalid map - missing type
   print("\n2️⃣ Testing invalid map (missing type)...")
   try:
       invalid_map = {"features": []}
       validator.validate_map_structure(invalid_map)
       print("   ❌ Invalid map should have failed")
   except ValidationError as e:
       print(f"   ✅ Correctly caught error: {e}")
   
   # Test 3: Invalid speed limit
   print("\n3️⃣ Testing invalid speed limit...")
   try:
       invalid_speed_map = create_sample_map()
       invalid_speed_map["features"][1]["properties"]["speed_limit"] = 5  # Too low
       validator.validate_map_structure(invalid_speed_map)
       print("   ❌ Invalid speed limit should have failed")
   except ValidationError as e:
       print(f"   ✅ Correctly caught error: {e}")
   
   print("\n🎉 Validator tests completed!")

if __name__ == "__main__":
   test_validator()