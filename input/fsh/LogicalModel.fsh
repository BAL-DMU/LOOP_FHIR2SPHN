Logical: Code
Parent: Base
Title: "SPHN Code Type"
* ^baseDefinition = "http://hl7.org/fhir/StructureDefinition/Base"
* iri 1..1 SU uri "" ""
* termid 1..1 SU string "" ""

Logical: CodeUID
Parent: Concept
Title: "SPHN Code Type (for UID)"
* hasCodingSystemAndVersion 1..1 SU string "" ""
* hasIdentifier 1..1 SU uri "" ""
* hasName 0..1 SU string "" ""

Logical: Concept
Parent: Element
Title: "SPHN Concept"
* ^baseDefinition = "http://hl7.org/fhir/StructureDefinition/Element"
* ^abstract = true

Logical: DataRelease
Parent: Concept
Title: "SPHN Data Release"
* creationTime 0..1 SU dateTime "" ""

Logical: DataProvider
Parent: Concept
Title: "SPHN Data Provider"
* hasInstitutionCode 1..1 SU CodeUID "" ""

Logical: SubjectPseudoIdentifier
Parent: Concept
Title: "SPHN SubjectPseudoIdentifier"
Characteristics: #can-be-target
* hasIdentifier 1..1 SU string "" ""

Logical: SourceSystem
Parent: Concept
Title: "SPHN Source System"
Characteristics: #can-be-target

Logical: LoopSphn
Parent: Base
Title: "LOOP SPHN"
* ^baseDefinition = "http://hl7.org/fhir/StructureDefinition/Base"
* content 1..1 SU Content "" "List of SPHN concepts"
* DataRelease 1..1 SU DataRelease "" ""
* DataProvider 1..1 SU DataProvider "" ""
* SubjectPseudoIdentifier 1..1 SU SubjectPseudoIdentifier "" ""

Logical: Content
Parent: Base
Title: "List of SPHN concepts"
* ^baseDefinition = "http://hl7.org/fhir/StructureDefinition/Base"
* BirthDate 0..* SU BirthDate "" ""
* Death 0..* SU Death "" ""
* DeathDate 0..* SU DeathDate "" ""
* AdministrativeSex 0..* SU AdministrativeSex "" ""
* AdministrativeCase 0..* SU AdministrativeCase "" ""
* BodyTemperatureMeasurement 0..* SU BodyTemperatureMeasurement "" ""
* BodyWeightMeasurement 0..* SU BodyWeightMeasurement "" ""
* BloodPressureMeasurement 0..* SU BloodPressureMeasurement "" ""
* HeartRateMeasurement 0..* SU HeartRateMeasurement "" ""
* OxygenSaturationMeasurement 0..* SU OxygenSaturationMeasurement "" ""
* Allergy 0..* SU Allergy "" ""
* LabTestEvent 0..* SU LabTestEvent "" ""
* ProblemCondition 0..* SU ProblemCondition "" ""
* SourceSystem 0..* SU SourceSystem "" ""

Logical: Location
Parent: Concept
Title: "SPHN Location"
* hasTypeCode 1..1 SU Code "" ""
* hasExact 0..1 SU string "" ""

Logical: CareHandling
Parent: Concept
Title: "SPHN Care Handling"
* hasTypeCode 1..1 SU Code "" ""

Logical: BirthDate
Parent: Concept
Title: "SPHN Birth Date"
* hasSourceSystem 1..* SU Reference(SourceSystem) "" ""
* hasYear 1..1 SU string "" ""
* hasMonth 0..1 SU string "" ""
* hasDay 0..1 SU string "" ""

Logical: DeathDate
Parent: Concept
Title: "SPHN Death Date"
Characteristics: #can-be-target
* hasYear 1..1 SU string "" ""
* hasMonth 0..1 SU string "" ""
* hasDay 0..1 SU string "" ""
* hasTime 0..1 SU time "" ""

Logical: Death
Parent: Concept
Title: "SPHN Death"
* hasSourceSystem 1..* SU Reference(SourceSystem) "" ""
* hasAdministrativeCase 0..1 SU Reference(AdministrativeCase) "" ""
* hasReportDateTime 0..1 SU dateTime "" ""
* hasDate 0..1 SU Reference(DeathDate) "" ""
* hasCircumstanceCode 0..1 SU Code "" ""
* hasConditionCode 0..1 SU Code "" ""

Logical: AdministrativeSex
Parent: Concept
Title: "SPHN Administrative Sex"
* hasSourceSystem 1..* SU Reference(SourceSystem) "" ""
* hasCode 1..1 SU Code "" ""
* hasRecordDateTime 0..1 SU dateTime "" ""

Logical: AdministrativeCase
Parent: Concept
Title: "SPHN Administrative Case"
Characteristics: #can-be-target
* hasSourceSystem 1..* SU Reference(SourceSystem) "" ""
* hasCareHandling 0..1 SU CareHandling "" ""
* hasAdmissionDateTime 1..1 SU dateTime "" ""
* hasDischargeDateTime 0..1 SU dateTime "" ""
* hasOriginLocation 0..1 SU Location "" ""
* hasDischargeLocation 0..1 SU Location "" ""

Logical: Measurement
Parent: Concept
Title: "SPHN Measurement"
* ^abstract = true
* hasSourceSystem 1..* SU Reference(SourceSystem) "" ""
* hasAdministrativeCase 0..1 SU Reference(AdministrativeCase) "" ""
* hasResult 1..* SU Result "" ""
* hasStartDateTime 1..1 SU dateTime "" ""
* hasEndDateTime 0..1 SU dateTime "" ""
* hasMethodCode 0..1 SU Code "" ""

Logical: Unit
Parent: Concept
Title: "SPHN Unit"
* hasCode 1..1 SU Code "" ""

Logical: Quantity
Parent: Concept
Title: "SPHN Quantity"
* hasValue 1..1 SU decimal "" ""
* hasUnit 1..1 SU Unit "" ""

Logical: Result
Parent: Concept
Title: "SPHN Result"
* ^abstract = true
// empty

Logical: Laterality
Parent: Concept
Title: "SPHN Laterality"
* hasCode 1..1 SU Code "" ""

Logical: BodySite
Parent: Concept
Title: "SPHN Body Site"
* hasCode 1..1 SU Code "" ""
* hasLaterality 0..1 SU Laterality "" ""

Logical: BodyTemperature
Parent: Result
Title: "SPHN Body Temperature"
* hasDateTime 0..1 SU dateTime "" ""
* hasQuantity 0..1 SU Quantity "" ""

Logical: BodyTemperatureMeasurement
Parent: Measurement
Title: "SPHN Body Temperature Measurement"
* hasResult[x] 1..* SU BodyTemperature "" ""

Logical: BodyWeight
Parent: Result
Title: "SPHN Body Weight"
* hasDateTime 0..1 SU dateTime "" ""
* hasQuantity 0..1 SU Quantity "" ""

Logical: BodyWeightMeasurement
Parent: Measurement
Title: "SPHN Body Weight Measurement"
* hasResult[x] 1..* SU BodyWeight "" ""

Logical: BloodPressure
Parent: Result
Title: "SPHN Blood Pressure"
* hasDateTime 0..1 SU dateTime "" ""
* hasMeanPressure 0..1 SU Quantity "" ""
* hasSystolicPressure 0..1 SU Quantity "" ""
* hasDiastolicPressure 0..1 SU Quantity "" ""

Logical: BloodPressureMeasurement
Parent: Measurement
Title: "SPHN Blood Pressure Measurement"
* hasResult[x] 1..* SU BloodPressure "" ""
* hasBodySite 0..1 SU BodySite "" ""

Logical: HeartRate
Parent: Result
Title: "SPHN Heart Rate"
* hasDateTime 0..1 SU dateTime "" ""
* hasQuantity 0..1 SU Quantity "" ""
* hasRegularityCode 0..1 SU Code "" ""

Logical: HeartRateMeasurement
Parent: Measurement
Title: "SPHN Heart Rate Measurement"
* hasResult[x] 1..* SU HeartRate "" ""

Logical: OxygenSaturation
Parent: Result
Title: "SPHN Oxygen Saturation"
* hasDateTime 0..1 SU dateTime "" ""
* hasQuantity 0..1 SU Quantity "" ""

Logical: OxygenSaturationMeasurement
Parent: Measurement
Title: "SPHN Oxygen Saturation Measurement"
* hasResult[x] 1..* SU OxygenSaturation "" ""

Logical: Allergen
Parent: Concept
Title: "SPHN Allergen"
* hasCode 1..* SU Code "" ""

Logical: Allergy
Parent: Concept
Title: "SPHN Allergy"
* hasSourceSystem 1..* SU Reference(SourceSystem) "" ""
* hasFirstRecordDatetime 0..1 SU dateTime "" ""
* hasAllergen 0..1 SU Allergen "" ""

Invariant: reference-range-or-value
Description: "Either ReferenceValue (hasQuantity) or ReferengeRange (hasLowerLimit, hasUpperLimit) but not both."
Severity: #error
Expression: "hasQuantity.exists() xor (hasLowerLimit.exists() or hasUpperLimit.exists())"

// Note: Combined ReferenceRange and ReferenceValue
// Cannot use choice for two reasons:
// 1) FML does currently not support this:
//      * hasNumericalReference[x] 0..1 SU ReferenceValue or ReferenceRange "" ""
// 2) the property in SPHN is always called 'hasNumericalReference' (and type specified in 'target_concept')
Logical: ReferenceRangeOrValue
Parent: Concept
Title: "SPHN Reference Range / Reference Value"
* obeys reference-range-or-value
* target_concept 1..1 SU url "" ""
* hasLowerLimit 0..1 SU Quantity "" ""
* hasUpperLimit 0..1 SU Quantity "" ""
* hasQuantity 0..1 SU Quantity "" ""

Logical: LabResult
Parent: Concept
Title: "SPHN Lab Result"
* hasCode 0..1 SU Code "" ""
* hasStringValue 0..1 SU string "" ""
* hasQuantity 0..1 SU Quantity "" ""
* hasNumericalReference 0..1 SU ReferenceRangeOrValue "" ""

Logical: LabTest
Parent: Concept
Title: "SPHN Lab Test"
* hasCode 1..1 SU Code "" ""
* hasResult 1..* SU LabResult "" ""

Logical: LabTestEvent
Parent: Concept
Title: "SPHN Lab Test Event"
* hasSourceSystem 1..* SU Reference(SourceSystem) "" ""
* hasAdministrativeCase 0..1 SU Reference(AdministrativeCase) "" ""
* hasReportDateTime 0..1 SU dateTime "" ""
* hasDateTime 0..1 SU dateTime "" ""
* hasLabTest 1..* SU LabTest "" ""

Logical: ProblemCondition
Parent: Concept
Title: "SPHN Problem Condition"
* hasSourceSystem 1..* SU Reference(SourceSystem) "" ""
* hasAdministrativeCase 0..1 SU Reference(AdministrativeCase) "" ""
* hasStringValue 0..1 SU string "" ""
* hasCode 0..1 SU Code "" ""
* hasOnsetDateTime 0..1 SU dateTime "" ""
* hasRecordDateTime 0..1 SU dateTime "" ""
