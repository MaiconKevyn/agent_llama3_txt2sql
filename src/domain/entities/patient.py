"""
Patient Entity - Core business object representing a patient in the SUS healthcare system
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass(frozen=True)
class Patient:
    """
    Patient entity representing a healthcare patient in the SUS system
    
    This entity encapsulates all patient-related data and business logic,
    ensuring data integrity and providing meaningful behavior.
    """
    age: int
    gender: int  # 1=Male, 3=Female based on SUS data standards
    municipality_residence: str
    state_residence: str
    city_residence: str
    latitude_residence: Optional[float] = None
    longitude_residence: Optional[float] = None
    
    def __post_init__(self):
        """Validate patient data after initialization"""
        self._validate()
    
    def _validate(self):
        """Validate patient data for business rules"""
        if not (0 <= self.age <= 150):
            raise ValueError(f"Patient age must be between 0 and 150, got {self.age}")
        
        if self.gender not in [1, 3]:
            raise ValueError(f"Gender must be 1 (Male) or 3 (Female), got {self.gender}")
        
        if not self.municipality_residence.strip():
            raise ValueError("Municipality residence cannot be empty")
        
        if not self.city_residence.strip():
            raise ValueError("City residence cannot be empty")
    
    @property
    def age_group(self) -> str:
        """Classify patient into age groups for analysis"""
        if self.age < 18:
            return "Menor"
        elif self.age < 65:
            return "Adulto"
        else:
            return "Idoso"
    
    @property
    def gender_description(self) -> str:
        """Get human-readable gender description"""
        return "Masculino" if self.gender == 1 else "Feminino"
    
    @property
    def is_elderly(self) -> bool:
        """Check if patient is elderly (65+ years)"""
        return self.age >= 65
    
    @property
    def is_minor(self) -> bool:
        """Check if patient is a minor (under 18 years)"""
        return self.age < 18
    
    def is_from_same_municipality(self, other_municipality: str) -> bool:
        """Check if patient is from the same municipality"""
        return self.municipality_residence.lower() == other_municipality.lower()
    
    def is_from_same_city(self, other_city: str) -> bool:
        """Check if patient is from the same city"""
        return self.city_residence.lower() == other_city.lower()
    
    def get_geographic_info(self) -> dict:
        """Get complete geographic information"""
        return {
            "municipality": self.municipality_residence,
            "state": self.state_residence,
            "city": self.city_residence,
            "latitude": self.latitude_residence,
            "longitude": self.longitude_residence
        }
    
    def get_demographic_summary(self) -> dict:
        """Get demographic summary for analysis"""
        return {
            "age": self.age,
            "age_group": self.age_group,
            "gender": self.gender_description,
            "is_elderly": self.is_elderly,
            "is_minor": self.is_minor,
            "location": f"{self.city_residence}, {self.state_residence}"
        }