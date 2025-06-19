"""
Diagnosis Entity - Represents medical diagnoses using ICD-10 classification
"""
from dataclasses import dataclass
from typing import Optional
import re


@dataclass(frozen=True)
class Diagnosis:
    """
    Diagnosis entity representing medical diagnoses in ICD-10 format
    
    Encapsulates diagnosis code validation and medical categorization logic
    according to international ICD-10 standards used in Brazilian healthcare.
    """
    primary_diagnosis_code: str
    death_cause_code: Optional[str] = None
    resulted_in_death: bool = False
    
    def __post_init__(self):
        """Validate diagnosis data after initialization"""
        self._validate()
    
    def _validate(self):
        """Validate diagnosis codes according to ICD-10 standards"""
        if not self._is_valid_icd10_format(self.primary_diagnosis_code):
            raise ValueError(f"Invalid ICD-10 format for primary diagnosis: {self.primary_diagnosis_code}")
        
        if self.death_cause_code and self.death_cause_code != "0":
            if not self._is_valid_icd10_format(self.death_cause_code):
                raise ValueError(f"Invalid ICD-10 format for death cause: {self.death_cause_code}")
    
    def _is_valid_icd10_format(self, code: str) -> bool:
        """Validate ICD-10 code format (e.g., A46, C168, J128)"""
        if not code or code == "0":
            return code == "0"  # "0" is valid for no death
        
        # ICD-10 pattern: Letter followed by 2-3 digits, optionally followed by decimal and 1-2 digits
        pattern = r'^[A-Z]\d{2,3}(\.\d{1,2})?$'
        return bool(re.match(pattern, code))
    
    @property
    def category(self) -> str:
        """Get ICD-10 category based on the first letter"""
        if not self.primary_diagnosis_code or self.primary_diagnosis_code == "0":
            return "Unknown"
        
        first_letter = self.primary_diagnosis_code[0].upper()
        
        categories = {
            'A': 'Doenças infecciosas e parasitárias (A00-B99)',
            'B': 'Doenças infecciosas e parasitárias (A00-B99)',
            'C': 'Neoplasias (C00-D48)',
            'D': 'Doenças do sangue e órgãos hematopoéticos e transtornos imunitários (D50-D89)',
            'E': 'Doenças endócrinas, nutricionais e metabólicas (E00-E90)',
            'F': 'Transtornos mentais e comportamentais (F00-F99)',
            'G': 'Doenças do sistema nervoso (G00-G99)',
            'H': 'Doenças do olho e anexos / Doenças do ouvido (H00-H95)',
            'I': 'Doenças do aparelho circulatório (I00-I99)',
            'J': 'Doenças do aparelho respiratório (J00-J99)',
            'K': 'Doenças do aparelho digestivo (K00-K93)',
            'L': 'Doenças da pele e do tecido subcutâneo (L00-L99)',
            'M': 'Doenças do sistema osteomuscular e do tecido conjuntivo (M00-M99)',
            'N': 'Doenças do aparelho geniturinário (N00-N99)',
            'O': 'Gravidez, parto e puerpério (O00-O99)',
            'P': 'Afecções originadas no período perinatal (P00-P96)',
            'Q': 'Malformações congênitas, deformidades e anomalias cromossômicas (Q00-Q99)',
            'R': 'Sintomas, sinais e achados anormais de exames clínicos e laboratoriais (R00-R99)',
            'S': 'Lesões, envenenamento e consequências de causas externas (S00-T98)',
            'T': 'Lesões, envenenamento e consequências de causas externas (S00-T98)',
            'V': 'Causas externas de morbidade e mortalidade (V01-Y98)',
            'W': 'Causas externas de morbidade e mortalidade (V01-Y98)',
            'X': 'Causas externas de morbidade e mortalidade (V01-Y98)',
            'Y': 'Causas externas de morbidade e mortalidade (V01-Y98)',
            'Z': 'Fatores que influenciam o estado de saúde e o contato com os serviços de saúde (Z00-Z99)'
        }
        
        return categories.get(first_letter, "Categoria não identificada")
    
    @property
    def is_chronic_condition(self) -> bool:
        """Determine if diagnosis represents a chronic condition"""
        if not self.primary_diagnosis_code or self.primary_diagnosis_code == "0":
            return False
        
        first_letter = self.primary_diagnosis_code[0].upper()
        
        # Categories that typically represent chronic conditions
        chronic_categories = ['C', 'E', 'F', 'G', 'I', 'J', 'K', 'M', 'N']
        return first_letter in chronic_categories
    
    @property
    def is_infectious_disease(self) -> bool:
        """Check if diagnosis is an infectious disease"""
        if not self.primary_diagnosis_code:
            return False
        return self.primary_diagnosis_code[0].upper() in ['A', 'B']
    
    @property
    def is_cancer(self) -> bool:
        """Check if diagnosis is cancer-related"""
        if not self.primary_diagnosis_code:
            return False
        return self.primary_diagnosis_code[0].upper() == 'C'
    
    @property
    def severity_indicator(self) -> str:
        """Get severity indicator based on outcome"""
        if self.resulted_in_death:
            return "Grave (resultou em óbito)"
        elif self.is_cancer:
            return "Grave (neoplasia)"
        elif self.is_chronic_condition:
            return "Moderada (condição crônica)"
        else:
            return "Leve a moderada"
    
    def is_related_to_death_cause(self) -> bool:
        """Check if primary diagnosis is related to death cause"""
        if not self.resulted_in_death or not self.death_cause_code or self.death_cause_code == "0":
            return False
        
        # Simple check if they're in the same category
        if len(self.primary_diagnosis_code) > 0 and len(self.death_cause_code) > 0:
            return self.primary_diagnosis_code[0] == self.death_cause_code[0]
        
        return False
    
    def get_medical_summary(self) -> dict:
        """Get complete medical summary"""
        return {
            "primary_diagnosis": self.primary_diagnosis_code,
            "category": self.category,
            "is_chronic": self.is_chronic_condition,
            "is_infectious": self.is_infectious_disease,
            "is_cancer": self.is_cancer,
            "severity": self.severity_indicator,
            "resulted_in_death": self.resulted_in_death,
            "death_cause": self.death_cause_code if self.death_cause_code != "0" else None
        }