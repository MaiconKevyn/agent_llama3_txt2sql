"""
Diagnosis Code Value Object - Immutable representation of ICD-10 diagnosis codes
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class DiagnosisCode:
    """
    Value object representing ICD-10 diagnosis codes with validation and categorization.
    
    Provides comprehensive medical categorization and validation according to
    international ICD-10 standards used in Brazilian healthcare system.
    """
    code: str
    
    def __post_init__(self):
        """Validate diagnosis code after initialization"""
        if not isinstance(self.code, str):
            raise TypeError("Diagnosis code must be a string")
        
        if not self._is_valid_format():
            raise ValueError(f"Invalid ICD-10 format: {self.code}")
    
    def _is_valid_format(self) -> bool:
        """Validate ICD-10 code format"""
        if self.code == "0":
            return True  # "0" represents no diagnosis/death
        
        if not self.code:
            return False
        
        # ICD-10 pattern: Letter + 2-3 digits + optional decimal + 1-2 digits
        pattern = r'^[A-Z]\d{2,3}(\.\d{1,2})?$'
        return bool(re.match(pattern, self.code.upper()))
    
    @property
    def category_letter(self) -> str:
        """Get the category letter (first character)"""
        if self.code == "0" or not self.code:
            return ""
        return self.code[0].upper()
    
    @property
    def category_name(self) -> str:
        """Get the full category name based on ICD-10 classification"""
        letter = self.category_letter
        
        categories = {
            'A': 'Doenças infecciosas e parasitárias',
            'B': 'Doenças infecciosas e parasitárias',
            'C': 'Neoplasias',
            'D': 'Doenças do sangue e órgãos hematopoéticos / Transtornos imunitários',
            'E': 'Doenças endócrinas, nutricionais e metabólicas',
            'F': 'Transtornos mentais e comportamentais',
            'G': 'Doenças do sistema nervoso',
            'H': 'Doenças do olho e anexos / Doenças do ouvido',
            'I': 'Doenças do aparelho circulatório',
            'J': 'Doenças do aparelho respiratório',
            'K': 'Doenças do aparelho digestivo',
            'L': 'Doenças da pele e do tecido subcutâneo',
            'M': 'Doenças do sistema osteomuscular e do tecido conjuntivo',
            'N': 'Doenças do aparelho geniturinário',
            'O': 'Gravidez, parto e puerpério',
            'P': 'Afecções originadas no período perinatal',
            'Q': 'Malformações congênitas e anomalias cromossômicas',
            'R': 'Sintomas e achados anormais de exames clínicos',
            'S': 'Lesões, envenenamento e consequências de causas externas',
            'T': 'Lesões, envenenamento e consequências de causas externas',
            'V': 'Causas externas de morbidade e mortalidade',
            'W': 'Causas externas de morbidade e mortalidade',
            'X': 'Causas externas de morbidade e mortalidade',
            'Y': 'Causas externas de morbidade e mortalidade',
            'Z': 'Fatores que influenciam o estado de saúde'
        }
        
        if letter == "":
            return "Sem diagnóstico"
        
        return categories.get(letter, "Categoria não identificada")
    
    @property
    def category_range(self) -> str:
        """Get the ICD-10 category code range"""
        letter = self.category_letter
        
        ranges = {
            'A': 'A00-B99', 'B': 'A00-B99',
            'C': 'C00-D48',
            'D': 'D50-D89',
            'E': 'E00-E90',
            'F': 'F00-F99',
            'G': 'G00-G99',
            'H': 'H00-H95',
            'I': 'I00-I99',
            'J': 'J00-J99',
            'K': 'K00-K93',
            'L': 'L00-L99',
            'M': 'M00-M99',
            'N': 'N00-N99',
            'O': 'O00-O99',
            'P': 'P00-P96',
            'Q': 'Q00-Q99',
            'R': 'R00-R99',
            'S': 'S00-T98', 'T': 'S00-T98',
            'V': 'V01-Y98', 'W': 'V01-Y98', 'X': 'V01-Y98', 'Y': 'V01-Y98',
            'Z': 'Z00-Z99'
        }
        
        return ranges.get(letter, "")
    
    @property
    def is_infectious_disease(self) -> bool:
        """Check if code represents an infectious disease"""
        return self.category_letter in ['A', 'B']
    
    @property
    def is_cancer(self) -> bool:
        """Check if code represents cancer/neoplasm"""
        return self.category_letter == 'C'
    
    @property
    def is_chronic_condition(self) -> bool:
        """Check if code typically represents a chronic condition"""
        # Categories that typically include chronic conditions
        chronic_categories = ['C', 'E', 'F', 'G', 'I', 'J', 'K', 'M', 'N']
        return self.category_letter in chronic_categories
    
    @property
    def is_external_cause(self) -> bool:
        """Check if code represents external causes (accidents, violence)"""
        return self.category_letter in ['S', 'T', 'V', 'W', 'X', 'Y']
    
    @property
    def is_mental_health(self) -> bool:
        """Check if code represents mental health conditions"""
        return self.category_letter == 'F'
    
    @property
    def is_respiratory(self) -> bool:
        """Check if code represents respiratory diseases"""
        return self.category_letter == 'J'
    
    @property
    def is_cardiovascular(self) -> bool:
        """Check if code represents cardiovascular diseases"""
        return self.category_letter == 'I'
    
    @property
    def severity_indicator(self) -> str:
        """Get general severity indicator based on category"""
        letter = self.category_letter
        
        high_severity = ['C', 'I', 'G']  # Cancer, cardiovascular, neurological
        medium_severity = ['J', 'K', 'N', 'E']  # Respiratory, digestive, renal, endocrine
        
        if letter in high_severity:
            return "Alta gravidade potencial"
        elif letter in medium_severity:
            return "Gravidade moderada"
        elif letter in ['S', 'T', 'V', 'W', 'X', 'Y']:
            return "Variável (causa externa)"
        else:
            return "Baixa a moderada gravidade"
    
    @property
    def subcategory(self) -> str:
        """Extract subcategory (numeric part) from the code"""
        if self.code == "0" or not self.code:
            return ""
        
        # Extract numeric part after the letter
        match = re.match(r'^[A-Z](\d+)', self.code)
        return match.group(1) if match else ""
    
    def is_in_range(self, start_code: str, end_code: str) -> bool:
        """Check if this code falls within a specified range"""
        try:
            # Simple comparison for codes in same category
            if (self.category_letter == start_code[0] == end_code[0] and
                start_code <= self.code <= end_code):
                return True
        except (IndexError, TypeError):
            pass
        return False
    
    def get_medical_classification(self) -> dict:
        """Get comprehensive medical classification"""
        return {
            "code": self.code,
            "category_letter": self.category_letter,
            "category_name": self.category_name,
            "category_range": self.category_range,
            "subcategory": self.subcategory,
            "is_infectious": self.is_infectious_disease,
            "is_cancer": self.is_cancer,
            "is_chronic": self.is_chronic_condition,
            "is_external_cause": self.is_external_cause,
            "is_mental_health": self.is_mental_health,
            "is_respiratory": self.is_respiratory,
            "is_cardiovascular": self.is_cardiovascular,
            "severity_indicator": self.severity_indicator
        }
    
    def compare_category_with(self, other_code: 'DiagnosisCode') -> str:
        """Compare category with another diagnosis code"""
        if self.category_letter == other_code.category_letter:
            return f"Mesma categoria ({self.category_name})"
        else:
            return f"Categorias diferentes: {self.category_name} vs {other_code.category_name}"