"""
Municipality Code Value Object - Immutable representation of Brazilian municipality codes
"""
from dataclasses import dataclass
from typing import Dict, Set


@dataclass(frozen=True)
class MunicipalityCode:
    """
    Value object representing Brazilian municipality codes (IBGE) with geographic
    classification and regional analysis capabilities.
    
    Provides validation and geographic categorization according to IBGE standards
    used in Brazilian administrative and healthcare systems.
    """
    code: str
    
    def __post_init__(self):
        """Validate municipality code after initialization"""
        if not isinstance(self.code, str):
            raise TypeError("Municipality code must be a string")
        
        if not self._is_valid_format():
            raise ValueError(f"Invalid Brazilian municipality code format: {self.code}")
    
    def _is_valid_format(self) -> bool:
        """Validate Brazilian municipality code format (6 digits)"""
        if not self.code or len(self.code) != 6:
            return False
        
        try:
            int(self.code)  # Must be numeric
            return True
        except ValueError:
            return False
    
    @property
    def state_code(self) -> str:
        """Get state code (first 2 digits)"""
        return self.code[:2]
    
    @property
    def municipality_number(self) -> str:
        """Get municipality number within state (last 4 digits)"""
        return self.code[2:]
    
    @property
    def state_name(self) -> str:
        """Get full state name based on code"""
        state_codes = {
            '11': 'Rondônia',
            '12': 'Acre',
            '13': 'Amazonas',
            '14': 'Roraima',
            '15': 'Pará',
            '16': 'Amapá',
            '17': 'Tocantins',
            '21': 'Maranhão',
            '22': 'Piauí',
            '23': 'Ceará',
            '24': 'Rio Grande do Norte',
            '25': 'Paraíba',
            '26': 'Pernambuco',
            '27': 'Alagoas',
            '28': 'Sergipe',
            '29': 'Bahia',
            '31': 'Minas Gerais',
            '32': 'Espírito Santo',
            '33': 'Rio de Janeiro',
            '35': 'São Paulo',
            '41': 'Paraná',
            '42': 'Santa Catarina',
            '43': 'Rio Grande do Sul',
            '50': 'Mato Grosso do Sul',
            '51': 'Mato Grosso',
            '52': 'Goiás',
            '53': 'Distrito Federal'
        }
        
        return state_codes.get(self.state_code, "Estado não identificado")
    
    @property
    def state_abbreviation(self) -> str:
        """Get state abbreviation"""
        abbreviations = {
            '11': 'RO', '12': 'AC', '13': 'AM', '14': 'RR', '15': 'PA',
            '16': 'AP', '17': 'TO', '21': 'MA', '22': 'PI', '23': 'CE',
            '24': 'RN', '25': 'PB', '26': 'PE', '27': 'AL', '28': 'SE',
            '29': 'BA', '31': 'MG', '32': 'ES', '33': 'RJ', '35': 'SP',
            '41': 'PR', '42': 'SC', '43': 'RS', '50': 'MS', '51': 'MT',
            '52': 'GO', '53': 'DF'
        }
        
        return abbreviations.get(self.state_code, "??")
    
    @property
    def geographic_region(self) -> str:
        """Get Brazilian geographic region"""
        regions = {
            # Norte
            '11': 'Norte', '12': 'Norte', '13': 'Norte', '14': 'Norte',
            '15': 'Norte', '16': 'Norte', '17': 'Norte',
            # Nordeste
            '21': 'Nordeste', '22': 'Nordeste', '23': 'Nordeste', '24': 'Nordeste',
            '25': 'Nordeste', '26': 'Nordeste', '27': 'Nordeste', '28': 'Nordeste',
            '29': 'Nordeste',
            # Sudeste
            '31': 'Sudeste', '32': 'Sudeste', '33': 'Sudeste', '35': 'Sudeste',
            # Sul
            '41': 'Sul', '42': 'Sul', '43': 'Sul',
            # Centro-Oeste
            '50': 'Centro-Oeste', '51': 'Centro-Oeste', '52': 'Centro-Oeste',
            '53': 'Centro-Oeste'
        }
        
        return regions.get(self.state_code, "Região não identificada")
    
    @property
    def is_capital(self) -> bool:
        """Check if municipality code represents a state capital"""
        # Common patterns for capital cities (ending in 020, but not exhaustive)
        capital_codes = {
            '110020',  # Porto Velho - RO
            '120040',  # Rio Branco - AC
            '130260',  # Manaus - AM
            '140010',  # Boa Vista - RR
            '150140',  # Belém - PA
            '160030',  # Macapá - AP
            '172100',  # Palmas - TO
            '211130',  # São Luís - MA
            '220440',  # Teresina - PI
            '230440',  # Fortaleza - CE
            '240810',  # Natal - RN
            '250750',  # João Pessoa - PB
            '261160',  # Recife - PE
            '270430',  # Maceió - AL
            '280030',  # Aracaju - SE
            '292740',  # Salvador - BA
            '310620',  # Belo Horizonte - MG
            '320530',  # Vitória - ES
            '330455',  # Rio de Janeiro - RJ
            '355030',  # São Paulo - SP
            '410690',  # Curitiba - PR
            '420540',  # Florianópolis - SC
            '431490',  # Porto Alegre - RS
            '500270',  # Campo Grande - MS
            '510340',  # Cuiabá - MT
            '520870',  # Goiânia - GO
            '530010'   # Brasília - DF
        }
        
        return self.code in capital_codes
    
    @property
    def is_metropolitan_area(self) -> bool:
        """Check if municipality is likely in a metropolitan area (simplified)"""
        # This is a simplified check based on common metropolitan area patterns
        metro_state_codes = ['31', '33', '35', '41', '42', '43']  # Major metropolitan states
        return self.state_code in metro_state_codes
    
    @property
    def economic_region_indicator(self) -> str:
        """Get economic development indicator based on region"""
        region = self.geographic_region
        
        economic_indicators = {
            'Sudeste': 'Alto desenvolvimento econômico',
            'Sul': 'Alto desenvolvimento econômico',
            'Centro-Oeste': 'Médio desenvolvimento econômico',
            'Nordeste': 'Desenvolvimento econômico em crescimento',
            'Norte': 'Desenvolvimento econômico emergente'
        }
        
        return economic_indicators.get(region, "Indicador não disponível")
    
    def is_same_state(self, other_code: 'MunicipalityCode') -> bool:
        """Check if this municipality is in the same state as another"""
        return self.state_code == other_code.state_code
    
    def is_same_region(self, other_code: 'MunicipalityCode') -> bool:
        """Check if this municipality is in the same geographic region as another"""
        return self.geographic_region == other_code.geographic_region
    
    def get_geographic_distance_indicator(self, other_code: 'MunicipalityCode') -> str:
        """Get relative geographic distance indicator"""
        if self.code == other_code.code:
            return "Mesmo município"
        elif self.is_same_state(other_code):
            return "Mesmo estado"
        elif self.is_same_region(other_code):
            return "Mesma região"
        else:
            return "Regiões diferentes"
    
    def get_complete_geographic_info(self) -> Dict[str, str]:
        """Get comprehensive geographic information"""
        return {
            "municipality_code": self.code,
            "state_code": self.state_code,
            "municipality_number": self.municipality_number,
            "state_name": self.state_name,
            "state_abbreviation": self.state_abbreviation,
            "geographic_region": self.geographic_region,
            "is_capital": self.is_capital,
            "is_metropolitan_area": self.is_metropolitan_area,
            "economic_indicator": self.economic_region_indicator
        }
    
    @classmethod
    def get_all_state_codes(cls) -> Set[str]:
        """Get all valid Brazilian state codes"""
        return {
            '11', '12', '13', '14', '15', '16', '17',  # Norte
            '21', '22', '23', '24', '25', '26', '27', '28', '29',  # Nordeste
            '31', '32', '33', '35',  # Sudeste
            '41', '42', '43',  # Sul
            '50', '51', '52', '53'  # Centro-Oeste
        }
    
    @classmethod
    def get_states_by_region(cls, region: str) -> Dict[str, str]:
        """Get all states in a specific region"""
        all_states = {
            '11': 'Rondônia', '12': 'Acre', '13': 'Amazonas', '14': 'Roraima',
            '15': 'Pará', '16': 'Amapá', '17': 'Tocantins',
            '21': 'Maranhão', '22': 'Piauí', '23': 'Ceará', '24': 'Rio Grande do Norte',
            '25': 'Paraíba', '26': 'Pernambuco', '27': 'Alagoas', '28': 'Sergipe', '29': 'Bahia',
            '31': 'Minas Gerais', '32': 'Espírito Santo', '33': 'Rio de Janeiro', '35': 'São Paulo',
            '41': 'Paraná', '42': 'Santa Catarina', '43': 'Rio Grande do Sul',
            '50': 'Mato Grosso do Sul', '51': 'Mato Grosso', '52': 'Goiás', '53': 'Distrito Federal'
        }
        
        region_mapping = {
            'Norte': ['11', '12', '13', '14', '15', '16', '17'],
            'Nordeste': ['21', '22', '23', '24', '25', '26', '27', '28', '29'],
            'Sudeste': ['31', '32', '33', '35'],
            'Sul': ['41', '42', '43'],
            'Centro-Oeste': ['50', '51', '52', '53']
        }
        
        state_codes = region_mapping.get(region, [])
        return {code: all_states[code] for code in state_codes if code in all_states}