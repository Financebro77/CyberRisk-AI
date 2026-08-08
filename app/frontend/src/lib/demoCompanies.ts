import type { CompanyBrief } from './types';

/**
 * Demo Mode — five realistic companies spanning the calibrated industries.
 * Each profile is a full CompanyBrief with differentiated revenue, data
 * volumes, security posture and policy terms, so a one-click run produces
 * meaningfully different loss outputs.  Recruiters can explore the platform
 * without typing any data.
 */

export interface DemoCompany {
  id: string;
  /** Card label (e.g. the industry). */
  name: string;
  /** Short tagline shown on the card. */
  blurb: string;
  /** Human profile shown in the detail strip. */
  profile: string;
  /** Risk posture hint (what the demo shows). */
  posture: 'Strong' | 'Moderate' | 'Weak';
  brief: CompanyBrief;
}

export const DEMO_COMPANIES: DemoCompany[] = [
  {
    id: 'healthcare',
    name: 'Healthcare',
    blurb: 'Regional health system · 2.1M patient records',
    profile:
      'Mid-sized hospital group with a large volume of protected health records, heavy clinical-system dependence and strict privacy obligations.',
    posture: 'Moderate',
    brief: {
      firm_name: 'Northfield Health System',
      industry: 'Healthcare',
      revenue_usd: 850_000_000,
      customer_records: 2_100_000,
      technology_dependency: 'High',
      country: 'United States',
      employees: 6_500,
      sensitive_records: 'Health / medical records',
      cloud_dependency: 'High',
      third_party_dependency: 'High',
      mfa_coverage: 'Comprehensive',
      pam: 'Defined',
      network_segmentation: 'Segmented',
      backup_strategy: 'Daily',
      vulnerability_management: 'Monthly',
      incident_response: 'Documented',
      previous_incidents: 1,
      existing_coverage: '$25M limit, $1M retention',
      risk_appetite: 'Retain up to $2M',
      policy_limit: 25_000_000,
      retention: 1_000_000,
    },
  },
  {
    id: 'bank',
    name: 'Bank',
    blurb: 'Commercial bank · $8.4B assets · 900k customers',
    profile:
      'Regional commercial bank with high-value financial data, a large digital channel and elevated regulatory and third-party exposure.',
    posture: 'Moderate',
    brief: {
      firm_name: 'Caledonia Commercial Bank',
      industry: 'Financial Services',
      revenue_usd: 1_600_000_000,
      customer_records: 900_000,
      technology_dependency: 'High',
      country: 'United Kingdom',
      employees: 4_200,
      sensitive_records: 'Payment card data',
      cloud_dependency: 'High',
      third_party_dependency: 'High',
      mfa_coverage: 'Comprehensive',
      pam: 'Segmented',
      network_segmentation: 'Segmented',
      backup_strategy: 'Continuous',
      vulnerability_management: 'Continuous',
      incident_response: 'Tested',
      previous_incidents: 2,
      existing_coverage: '$50M limit, $2M retention',
      risk_appetite: 'Retain up to $3M',
      policy_limit: 50_000_000,
      retention: 2_000_000,
    },
  },
  {
    id: 'manufacturing',
    name: 'Manufacturing',
    blurb: 'Industrial manufacturer · $520M revenue',
    profile:
      'Mid-market manufacturer with OT/ICS exposure, a broad supplier network and partial segmentation across production and IT.',
    posture: 'Weak',
    brief: {
      firm_name: 'Ironclad Manufacturing',
      industry: 'Manufacturing',
      revenue_usd: 520_000_000,
      customer_records: 150_000,
      technology_dependency: 'Moderate',
      country: 'Germany',
      employees: 3_100,
      sensitive_records: 'Intellectual property',
      cloud_dependency: 'Moderate',
      third_party_dependency: 'High',
      mfa_coverage: 'Partial',
      pam: 'Basic',
      network_segmentation: 'Basic',
      backup_strategy: 'Daily',
      vulnerability_management: 'Monthly',
      incident_response: 'Ad-hoc',
      previous_incidents: 3,
      existing_coverage: '$10M limit, $500k retention',
      risk_appetite: 'Retain up to $1.5M',
      policy_limit: 10_000_000,
      retention: 500_000,
    },
  },
  {
    id: 'retail',
    name: 'Retail',
    blurb: 'E-commerce retailer · 5.2M customers · card processing',
    profile:
      'Consumer retailer running a large card-transaction surface across web and POS, with strong dependency on cloud checkout infrastructure.',
    posture: 'Moderate',
    brief: {
      firm_name: 'Meridian Market',
      industry: 'Retail',
      revenue_usd: 1_100_000_000,
      customer_records: 5_200_000,
      technology_dependency: 'High',
      country: 'United States',
      employees: 8_000,
      sensitive_records: 'Payment card data',
      cloud_dependency: 'High',
      third_party_dependency: 'Moderate',
      mfa_coverage: 'Partial',
      pam: 'Defined',
      network_segmentation: 'Basic',
      backup_strategy: 'Daily',
      vulnerability_management: 'Weekly',
      incident_response: 'Documented',
      previous_incidents: 1,
      existing_coverage: '$20M limit, $750k retention',
      risk_appetite: 'Retain up to $2M',
      policy_limit: 20_000_000,
      retention: 750_000,
    },
  },
  {
    id: 'energy',
    name: 'Energy',
    blurb: 'Energy utility · grid & OT infrastructure',
    profile:
      'Regional utility with industrial control systems, critical-infrastructure obligations and exposure to OT/physical disruption scenarios.',
    posture: 'Strong',
    brief: {
      firm_name: 'Apex Energy Cooperative',
      industry: 'Energy',
      revenue_usd: 3_200_000_000,
      customer_records: 1_400_000,
      technology_dependency: 'High',
      country: 'Canada',
      employees: 5_700,
      sensitive_records: 'Customer PII',
      cloud_dependency: 'Moderate',
      third_party_dependency: 'Moderate',
      mfa_coverage: 'Comprehensive',
      pam: 'Segmented',
      network_segmentation: 'Segmented',
      backup_strategy: 'Continuous',
      vulnerability_management: 'Continuous',
      incident_response: 'Tested',
      previous_incidents: 1,
      existing_coverage: '$30M limit, $1.5M retention',
      risk_appetite: 'Retain up to $2.5M',
      policy_limit: 30_000_000,
      retention: 1_500_000,
    },
  },
];
