Logical: Code
Parent: Base
Title: "SPHN Code Type"
* ^baseDefinition = "http://hl7.org/fhir/StructureDefinition/Base"
* iri 1..1 SU uri "" ""
* termid 1..1 SU string "" ""

Logical: Concept
Parent: Element
Title: "SPHN Concept"
* ^baseDefinition = "http://hl7.org/fhir/StructureDefinition/Element"

Logical: DataRelease
Parent: Concept
Title: "SPHN DataRelease"
* creationTime 0..1 SU dateTime "" ""

Logical: SubjectPseudoIdentifier
Parent: Concept
Title: "SPHN SubjectPseudoIdentifier"
Characteristics: #can-be-target
* hasIdentifier 1..1 SU string "" ""

Logical: LoopSphn
Parent: Base
Title: "LOOP SPHN"
* ^baseDefinition = "http://hl7.org/fhir/StructureDefinition/Base"
* content 1..1 SU Content "" "List of SPHN concepts"
* DataRelease 1..1 SU DataRelease "" ""
* SubjectPseudoIdentifier 1..1 SU SubjectPseudoIdentifier "" ""

Logical: Content
Parent: Base
Title: "List of SPHN concepts"
* ^baseDefinition = "http://hl7.org/fhir/StructureDefinition/Base"
* BirthDate 0..* SU BirthDate "" ""
* AdministrativeSex 0..* SU AdministrativeSex "" ""
* AdministrativeCase 0..* SU AdministrativeCase "" ""
//* BodyTemperatureMeasurement 0..* SU BodyTemperatureMeasurement "some value" "description of value"

Logical: Location
Parent: Concept
Title: "SPHN Location"
* hasTypeCode 1..1 SU Code "" ""
* hasExact 1..1 SU string "" ""

Logical: BirthDate
Parent: Concept
Title: "SPHN BirthDate"
* hasYear 1..1 SU string "" ""
* hasMonth 1..1 SU string "" ""
* hasDay 1..1 SU string "" ""

Logical: AdministrativeSex
Parent: Concept
Title: "SPHN AdministrativeSex"
* hasCode 1..1 SU Code "" ""
* hasRecordDateTime 1..1 SU dateTime "" ""

Logical: AdministrativeCase
Parent: Concept
Title: "SPHN AdministrativeCase"
Characteristics: #can-be-target
* Identifier 1..1 SU string "" ""
* hasAdmissionDateTime 1..1 SU dateTime "" ""
* hasDischargeDateTime 0..1 SU dateTime "" "" 
* hasOriginLocation 0..1 SU Location "" ""
