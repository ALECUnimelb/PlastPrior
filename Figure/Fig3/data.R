hazard_components <- c(
  Persistence = "Persistence_score",
  Bioaccumulation = "Bioaccumulation_score",
  Mobility = "Mobility_score",
  Toxicity = "Toxicity_score"
)

exposure_indicators <- c(
  "Inventory presence" = "Exposure_inventory_score",
  "Production / market" = "Exposure_production_score",
  Patents = "Exposure_patent_score",
  Literature = "Exposure_literature_score",
  "Food-contact migration" = "Exposure_food_contact_score",
  "Human biomonitoring" = "Exposure_human_biomonitoring_score"
)

exposure_dimensions <- list(
  "Inventory presence" = "Exposure_inventory_score",
  "Production / market" = "Exposure_production_score",
  Patents = "Exposure_patent_score",
  Literature = "Exposure_literature_score",
  "Food-contact + biomonitoring" = c(
    "Exposure_food_contact_score", "Exposure_human_biomonitoring_score"
  )
)

exposure_indicator_status_columns <- list(
  "Inventory presence" = "Exposure_inventory_data_status",
  "Production / market" = "Exposure_production_data_status",
  Patents = "Exposure_patent_data_status",
  Literature = "Exposure_literature_data_status",
  "Food-contact migration" = "Exposure_food_contact_data_status",
  "Human biomonitoring" = "Exposure_FCChumon_detection_data_status"
)

regulatory_status_map <- c(
  prohibited_or_phaseout = "Prohibited/phase-out",
  restricted_or_authorisation_required = "Restricted/authorisation",
  candidate_or_high_concern = "Candidate/high concern",
  monitoring_reporting_or_hazard_classification = "Monitoring/reporting/hazard",
  inventory_registration_or_use_only = "Inventory/registration/use",
  auxiliary_identifier_only = "No matched GIC listing",
  not_listed = "No matched GIC listing"
)
