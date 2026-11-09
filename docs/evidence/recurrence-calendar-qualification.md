# Recurrence and calendar qualification

The audited runtime is `449dc04c17a9c41d949d74cd341bf1e943a2fba9`.
Its [develop CI](https://github.com/vypdev/domus/actions/runs/42570153605) passed.
The package qualification extends the calendar image test to the actual app
launcher and four independent owned installations. Earlier receipts stay in
[the lifecycle evidence](recurrence-lifecycle-calendar.json).

The review tracks 93 owning cases, 21 lifecycle refinements, seven native
calendar cases, and 22 required integration aliases. Each row names the
assertions or suites to inspect. A **Witness** identifies a direct automated
acceptance path. A **Partial** row records the missing assertion or context.
A **Gap** records missing product behavior. Shared tests and aliases do not add
executions. Check the run on the tested revision before treating a witness as
executed. Owner acceptance and distribution qualification are separate gates.

The concrete product gaps are the active household category reference, the
calendar's distinct-occurrence count, and visible calendar attention for
preserved downstream work. The corresponding retained cases below stay open.
Independent combined journeys and owner review also remain outstanding. The
Points and Inventory consumers own their respective cross-domain acceptance.


## Calendar owner

See the [owning specification](../../specs/recurrence-calendar.md).

| Case | Evidence status | Automated witness or remaining assertion |
| --- | --- | --- |
| recurrence-calendar-C01 | Witness | `tests/backend/test_calendar_boundaries.py::test_late_completion_keeps_saturday_anchor_and_member_filters_distinguish_history`. Both protected compositions expose the next Saturday after an actual Monday completion. |
| recurrence-calendar-C02 | Witness | `tests/backend/test_nominal_recurrence.py::test_monthly_31_omits_invalid_month_without_losing_original_day_anchor` |
| recurrence-calendar-C03 | Witness | `tests/backend/test_recurrence_rules.py::test_raw_rule_rejects_duplicates_unsupported_parts_malformed_dates_and_unbounded_numbers` |
| recurrence-calendar-C04 | Witness | `tests/backend/test_relative_recurrence_planning.py::test_approval_days_later_keeps_the_actual_performed_local_day_and_original_source` |
| recurrence-calendar-C05 | Witness | `tests/backend/test_relative_lifecycle_consumer.py::test_reopening_only_cancels_proven_unstarted_work` |
| recurrence-calendar-C06 | Witness | `tests/backend/test_calendar_http.py::test_calendar_marks_a_retained_successor_after_source_reopening`, `frontend/tests/e2e/catalog.spec.ts`. The original attention receipt survives restart. Both protected compositions show the retained work with unchanged entry identities, and the compiled calendar renders the warning in both languages. |
| recurrence-calendar-C07 | Witness | `tests/backend/test_fixed_materialization.py::test_actual_independent_step_writers_have_one_complete_winner` |
| recurrence-calendar-C08 | Witness | `tests/backend/test_fair_recurrence.py::test_repeated_restart_after_every_first_step_cannot_starve_the_other_ninety_eight_rules` |
| recurrence-calendar-C09 | Witness | `tests/backend/test_fair_recurrence.py::test_actual_global_thousand_slot_limit_retains_the_next_obligation_for_another_tick` |
| recurrence-calendar-C10 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_gap_selects_first_valid_boundary_instead_of_shifting_entire_gap`, `tests/backend/test_calendar_queries.py::test_timed_planned_fact_keeps_nominal_and_gap_adjusted_time` |
| recurrence-calendar-C11 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_fold_selects_exactly_one_requested_actual_utc_appearance`, `tests/backend/test_recurrence_runtime.py` |
| recurrence-calendar-C12 | Witness | `frontend/tests/calendar-component.test.ts`, `tests/backend/test_calendar_queries.py::test_date_only_slots_keep_original_and_effective_dates_through_move` |
| recurrence-calendar-C13 | Witness | `tests/backend/test_recurrence_review.py::test_fixed_pause_and_resume_preview_retained_and_unmaterialized_work`, `tests/backend/test_fixed_materialization.py::test_paused_rule_has_no_effect_and_pause_after_planning_invalidates_the_write` |
| recurrence-calendar-C14 | Witness | `tests/backend/test_fixed_batch_review.py::test_second_replacement_distinguishes_proven_old_cancellations_from_retained_work`, `tests/backend/test_recurrence_review.py::test_prospective_pattern_change_preserves_issued_work_and_restarts_after_its_frontier` |
| recurrence-calendar-C15 | Witness | `tests/backend/test_fixed_exception_review.py::test_preview_rebuild_preserves_exception_identity_and_reuses_only_remaining_slots`, `tests/backend/test_recurrence_review.py::test_reschedule_preserves_original_slot_and_moves_effective_deadline` |
| recurrence-calendar-C16 | Witness | `frontend/tests/calendar-component.test.ts`, `frontend/tests/e2e/workspace-navigation.spec.ts` |
| recurrence-calendar-C17 | Witness | `frontend/tests/e2e/catalog.spec.ts` |
| recurrence-calendar-C18 | Witness | `frontend/tests/calendar-component.test.ts`, `tests/backend/test_calendar_queries.py::test_date_only_slots_keep_original_and_effective_dates_through_move` |
| recurrence-calendar-C19 | Witness | `tests/backend/test_calendar_boundaries.py::test_late_completion_keeps_saturday_anchor_and_member_filters_distinguish_history`. Both compositions authorize the current member before returning its assigned facts, and mask them after suspension or for a foreign filter identity. |
| recurrence-calendar-C20 | Witness | `tests/backend/test_calendar_boundaries.py::test_excessive_calendar_range_returns_the_actual_supported_limit`, `frontend/tests/calendar-component.test.ts`. The HTTP response names the accepted 366-day bound. The component preserves the submitted date and filters after a rejected read. |
| recurrence-calendar-C21 | Gap | `tests/backend/test_calendar_queries.py::test_combined_filters_count_actual_performers_independently_of_assignees`. The current category predicate matches free-text tags. The contract calls for household category references. |
| recurrence-calendar-C22 | Witness | `tests/backend/test_ha_calendar_projection.py::test_ha_projection_keeps_uids_offsets_and_date_only_markers_through_retry`, `tests/ha/calendar_smoke.py` |
| recurrence-calendar-C23 | Witness | `tests/ha/calendar_smoke.py` |
| recurrence-calendar-C24 | Partial | `tests/containers/test_app_image.py::test_calendar_core_uses_both_exact_packaged_compositions`, `tests/backend/test_ha_calendar_installation.py`. Internal-only networking and the disabled sync contract are covered. Retain an owner configuration check at installation. |
| recurrence-calendar-C25 | Witness | `tests/backend/test_relative_recurrence_planning.py::test_approval_days_later_keeps_the_actual_performed_local_day_and_original_source` |
| recurrence-calendar-C26 | Witness | `tests/backend/test_relative_lifecycle_consumer.py::test_late_approval_reuses_generation_and_rejection_reopen_reuses_invalidation`, `tests/backend/test_relative_lifecycle_consumer.py::test_verification_visibility_binds_original_approval_without_moving_actual_work` |
| recurrence-calendar-C27 | Partial | `tests/backend/test_relative_lifecycle_consumer.py::test_actual_completion_advances_one_successor_and_replays_original_after_restart`. Recurrence verifies the successor and retained completion state. Ledger acceptance belongs to the Points consumer. |
| recurrence-calendar-C28 | Witness | `tests/backend/test_relative_lifecycle_consumer.py::test_verification_visibility_binds_original_approval_without_moving_actual_work`, `tests/backend/test_recurrence_review.py::test_settings_never_reinterpret_pending_completion_or_overwrite_changed_work` |
| recurrence-calendar-C29 | Partial | `tests/backend/test_missed_occurrence_policy.py::test_default_keeps_each_slot_pending_and_switch_requires_an_explicit_skip`. Original missed slots and fixed anchor are exercised. Cross-domain award checks follow the Points consumer. |
| recurrence-calendar-C30 | Witness | `tests/backend/test_recurrence_review.py::test_fixed_overdue_skip_keeps_slot_and_task_history_without_affecting_later_work`, `tests/backend/test_recurrence_http.py::test_protected_overdue_fixed_skip_recovers_original_exception` |
| recurrence-calendar-C31 | Witness | `frontend/tests/e2e/tasks.spec.ts` (protected calendar and fixed batch review in native and standalone, EN and ES), `tests/backend/test_fixed_batch_review.py::test_second_replacement_distinguishes_proven_old_cancellations_from_retained_work`. An installed preview retains started work; recovery preserves the original completed cycle and cancels only reviewed future work. |
| recurrence-calendar-C32 | Witness | `tests/backend/test_fixed_batch_review.py::test_concurrent_start_fences_replacement_and_post_effect_failure_rolls_back` |
| recurrence-calendar-C33 | Partial | `frontend/tests/e2e/tasks.spec.ts` (protected calendar and fixed batch review), `tests/backend/test_fixed_batch_review.py::test_replacement_commits_one_linked_batch_and_recovers_by_original_key`. An intercepted committed response recovers by the same key with no second POST; the original and replacement remain linked. Inventory reservations require the owning consumer. |
| recurrence-calendar-C34 | Witness | `tests/backend/test_fixed_batch_review.py::test_prior_manual_move_remains_blocking_when_its_effective_deadline_escapes_the_review`, `tests/backend/test_fixed_exception_review.py::test_addition_cannot_collide_with_a_rescheduled_task` |
| recurrence-calendar-C35 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_fold_selects_exactly_one_requested_actual_utc_appearance`, `tests/backend/test_fixed_materialization.py::test_replaying_a_proved_current_slot_advances_progress_without_duplicate_work` |
| recurrence-calendar-C36 | Witness | `tests/backend/test_ha_calendar_projection.py::test_ha_projection_keeps_uids_offsets_and_date_only_markers_through_retry`, `tests/backend/test_recurrence_review.py::test_attachment_snapshots_household_fold_and_replays_after_preference_changes` |
| recurrence-calendar-C37 | Witness | `tests/backend/test_fixed_batch_review.py::test_fold_replacement_cannot_cancel_first_appearance_once_due`, `tests/backend/test_recurrence_review.py::test_prospective_fixed_fold_snapshots_policy_beyond_issued_work` |

## Execution foundation

See the [owning specification](../../specs/recurrence-execution-foundation.md).

| Case | Evidence status | Automated witness or remaining assertion |
| --- | --- | --- |
| recurrence-execution-C01 | Witness | `tests/backend/test_nominal_recurrence.py`, `tests/backend/test_recurrence_rules.py::test_strict_rule_parser_supports_all_declared_parts_without_provider_defaults` |
| recurrence-execution-C02 | Witness | `tests/backend/test_recurrence_rules.py::test_raw_rule_rejects_duplicates_unsupported_parts_malformed_dates_and_unbounded_numbers` |
| recurrence-execution-C03 | Witness | `tests/backend/test_recurrence_cursor_integrity.py::test_actual_bounded_progress_remains_valid_through_empty_periods_count_until_and_exhaustion`, `tests/backend/test_fixed_exception_review.py::test_exclusion_consumes_a_counted_nominal_and_addition_has_own_proof` |
| recurrence-execution-C04 | Witness | `tests/backend/test_recurrence_rules.py::test_raw_rule_rejects_duplicates_unsupported_parts_malformed_dates_and_unbounded_numbers`, `tests/backend/test_schedule_creation_http.py::test_atomic_scheduled_creation_and_original_recovery`. Both protected compositions reject unsupported rule parts and out-of-bounds intervals before any task or rule is written. |
| recurrence-execution-C05 | Gap | `tests/backend/test_calendar_queries.py::test_combined_filters_count_actual_performers_independently_of_assignees`. Task content uses tags and has no category reference to validate against the active household catalog. |
| recurrence-execution-C06 | Witness | `tests/backend/test_schedule_creation_http.py::test_atomic_scheduled_creation_and_original_recovery`, `tests/backend/test_task_http.py::test_title_only_create_detail_history_and_own_operation_replay`, `frontend/tests/e2e/tasks.spec.ts`. Both scheduled creation modes preserve the manual title-only path, defer first materialization and recover a lost browser response without a duplicate. |
| recurrence-execution-C07 | Witness | `tests/backend/test_recurrence_review.py::test_manual_adoption_binds_exact_existing_work_and_replays_after_restart`, `tests/backend/test_recurrence_review.py::test_attach_unconfigured_definition_preserves_manual_work_and_recovers_original` |
| recurrence-execution-C08 | Witness | `tests/backend/test_nominal_recurrence.py::test_interval_and_week_start_keep_phase_across_december_and_empty_periods`, `tests/backend/test_recurrence_rules.py::test_explicit_defaults_and_canonical_selector_order_preserve_original_anchor` |
| recurrence-execution-C09 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_gap_selects_first_valid_boundary_instead_of_shifting_entire_gap`, `tests/backend/test_calendar_queries.py::test_timed_planned_fact_keeps_nominal_and_gap_adjusted_time` |
| recurrence-execution-C10 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_gap_selects_first_valid_boundary_instead_of_shifting_entire_gap` |
| recurrence-execution-C11 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_fold_selects_exactly_one_requested_actual_utc_appearance`, `tests/backend/test_recurrence_local_instant.py::test_actual_fold_is_preserved_even_when_household_prefers_the_other_appearance` |
| recurrence-execution-C12 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_whole_date_adjustment_keeps_distinct_nominal_slots_when_instants_collide` |
| recurrence-execution-C13 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_adapter_does_not_consult_or_mutate_process_timezone_path`, `tests/backend/test_recurrence_time_adapter.py::test_missing_or_incompatible_package_never_uses_machine_timezone_fallback` |
| recurrence-execution-C14 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_unknown_zone_is_input_failure_not_silent_utc_or_source_unavailability`, `tests/backend/test_recurrence_time_adapter.py::test_actual_resource_failures_have_bounded_safe_distinct_results` |
| recurrence-execution-C15 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_relative_target_date_overflow_fails_instead_of_wrapping`, `tests/backend/test_recurrence_time_adapter.py::test_actual_zone_can_overflow_utc_even_when_nominal_calendar_date_is_valid`, `tests/backend/test_recurrence_local_instant.py::test_local_at_rejects_noninstant_or_out_of_range_input` |
| recurrence-execution-C16 | Witness | `tests/backend/test_fair_recurrence.py`, `tests/backend/test_recurrence_runtime.py::test_saved_household_horizon_limits_next_worker_run_in_both_compositions` |
| recurrence-execution-C17 | Witness | `tests/backend/test_fixed_materialization.py::test_actual_independent_step_writers_have_one_complete_winner`, `tests/backend/test_relative_lifecycle_consumer.py::test_independent_writers_commit_one_original_and_one_successor` |
| recurrence-execution-C18 | Witness | `tests/backend/test_fixed_materialization.py::test_failure_after_any_new_effect_rolls_back_task_cursor_and_command_proofs`, `tests/backend/test_relative_lifecycle_consumer.py::test_fault_after_writing_effect_proof_or_acknowledgement_rolls_back` |
| recurrence-execution-C19 | Witness | `tests/backend/test_fixed_materialization.py::test_restart_at_terminal_cursor_creates_no_more_work_or_evidence`, `tests/backend/test_relative_lifecycle_consumer.py::test_actual_completion_advances_one_successor_and_replays_original_after_restart` |
| recurrence-execution-C20 | Witness | `tests/backend/test_fixed_materialization.py::test_rule_snapshot_used_for_a_horizon_cannot_change_before_the_step`, `tests/backend/test_relative_lifecycle_consumer.py::test_changed_or_missing_live_inputs_cannot_commit_the_observed_completion` |
| recurrence-execution-C21 | Witness | `tests/backend/test_recurrence_review.py::test_fixed_pause_and_resume_preview_retained_and_unmaterialized_work`, `tests/backend/test_fixed_materialization.py::test_paused_rule_has_no_effect_and_pause_after_planning_invalidates_the_write` |
| recurrence-execution-C22 | Witness | `tests/backend/test_recurrence_worker.py::test_close_waits_for_admitted_step_and_prevents_another_tick`, `tests/backend/test_recurrence_runtime.py::test_owned_runtime_keeps_actual_installation_lease_until_its_worker_has_joined` |
| recurrence-execution-C23 | Witness | `tests/backend/test_recurrence_qualification.py::test_calendar_stays_pending_when_the_watermark_has_passed_unresolved_work`, `tests/backend/test_recurrence_qualification.py::test_nonactionable_final_scan_unit_keeps_the_next_source_for_a_fresh_runner` |
| recurrence-execution-C24 | Partial | `tests/backend/test_relative_lifecycle_consumer.py::test_actual_completion_advances_one_successor_and_replays_original_after_restart`. Pending approval does not block the default successor. Confirm the absence of a Points award when its consumer is available. |
| recurrence-execution-C25 | Witness | `tests/backend/test_relative_lifecycle_consumer.py::test_verification_visibility_binds_original_approval_without_moving_actual_work` |
| recurrence-execution-C26 | Witness | `tests/backend/test_relative_lifecycle_consumer.py::test_reopening_only_cancels_proven_unstarted_work`, `tests/backend/test_relative_lifecycle_consumer.py::test_late_approval_reuses_generation_and_rejection_reopen_reuses_invalidation` |
| recurrence-execution-C27 | Partial | `tests/backend/test_relative_lifecycle_consumer.py::test_reopening_only_cancels_proven_unstarted_work`, `tests/backend/test_relative_lifecycle_consumer.py::test_restore_retains_a_downstream_start_even_if_current_work_looks_unstarted`. Preservation is covered. Cross-domain compensation requires the Points and Inventory consumers. |
| recurrence-execution-C28 | Witness | `tests/backend/test_recurrence_source_observations.py::test_original_snapshots_are_bounded_ordered_and_independent_of_delivery`, `tests/backend/test_relative_lifecycle_consumer.py::test_terminal_cycle_before_or_after_generation_never_grants_twice` |
| recurrence-execution-C29 | Witness | `tests/backend/test_recurrence_time_adapter.py::test_relative_successor_adds_local_days_to_actual_work_not_elapsed_utc_hours`, `tests/backend/test_relative_recurrence_planning.py::test_approval_days_later_keeps_the_actual_performed_local_day_and_original_source` |
| recurrence-execution-C30 | Witness | `tests/backend/test_relative_lifecycle_consumer.py::test_restore_of_later_completion_fences_an_absent_original_without_generating`, `tests/backend/test_relative_lifecycle_consumer.py::test_compatible_restore_copies_later_cycle_proof_without_the_successor` |
| recurrence-execution-C31 | Witness | `tests/backend/test_fixed_batch_review.py::test_second_replacement_distinguishes_proven_old_cancellations_from_retained_work`, `tests/backend/test_recurrence_review.py::test_prospective_pattern_change_preserves_issued_work_and_restarts_after_its_frontier` |
| recurrence-execution-C32 | Witness | `tests/backend/test_fixed_batch_review.py::test_concurrent_start_fences_replacement_and_post_effect_failure_rolls_back` |
| recurrence-execution-C33 | Witness | `tests/backend/test_fixed_exception_review.py::test_preview_rebuild_preserves_exception_identity_and_reuses_only_remaining_slots`, `tests/backend/test_recurrence_review.py::test_reschedule_preserves_original_slot_and_moves_effective_deadline` |
| recurrence-execution-C34 | Witness | `tests/backend/test_fixed_batch_review.py::test_replacement_commits_one_linked_batch_and_recovers_by_original_key`, `tests/backend/test_fixed_batch_review.py::test_batch_http_routes_apply_and_recover_in_both_compositions` |
| recurrence-execution-C35 | Partial | `tests/backend/test_recurrence_time_adapter.py::test_whole_date_adjustment_keeps_distinct_nominal_slots_when_instants_collide`, `tests/backend/test_fixed_exception_review.py::test_timed_addition_uses_resolved_instants_for_collisions`. Confirm the collision is visible in the real reviewed plan rather than only detectable in the adapter and command. |
| recurrence-execution-C36 | Witness | `tests/backend/test_fixed_batch_review.py::test_batch_replacement_snapshots_household_fold_and_rejects_changed_preference`, `tests/backend/test_fixed_batch_review.py::test_fold_replacement_cannot_cancel_first_appearance_once_due` |
| recurrence-execution-C37 | Witness | `tests/backend/test_calendar_queries.py::test_date_only_slots_keep_original_and_effective_dates_through_move`, `frontend/tests/calendar-component.test.ts` |
| recurrence-execution-C38 | Witness | `tests/backend/test_calendar_http.py::test_calendar_http_requires_current_context_and_closed_range`, `tests/backend/test_calendar_queries.py::test_date_only_slots_keep_original_and_effective_dates_through_move`, `tests/backend/test_ha_calendar_installation.py::test_calendar_bearer_is_only_for_its_scoped_read_and_rotates` |
| recurrence-execution-C39 | Gap | `tests/backend/test_calendar_queries.py::test_combined_filters_count_actual_performers_independently_of_assignees`. The calendar has one event-row count. It lacks a distinct-occurrence count and a genuine category predicate. |
| recurrence-execution-C40 | Witness | `tests/backend/test_calendar_boundaries.py::test_late_completion_keeps_saturday_anchor_and_member_filters_distinguish_history`. Actual planned and due assignees, Monday performance and verifier facts remain separate in both protected compositions. |
| recurrence-execution-C41 | Witness | `tests/backend/test_calendar_queries.py::test_distinct_task_count_preserves_both_completion_cycle_identities`, `tests/backend/test_ha_calendar_projection.py::test_ha_projection_keeps_uids_offsets_and_date_only_markers_through_retry` |
| recurrence-execution-C42 | Witness | `tests/backend/test_calendar_http.py::test_calendar_outage_honors_current_permissions_and_original_read_deadline` |
| recurrence-execution-C43 | Partial | `tests/backend/test_recurrence_review.py::test_preview_scope_payload_expiry_and_current_authority_are_required`, `tests/backend/test_recurrence_http.py::test_protected_review_preview_apply_and_original_receipt`. Scope and current authority are covered. Record explicit HA rejection followed by recovery on both routes. |
| recurrence-execution-C44 | Witness | `tests/backend/test_fixed_materialization.py::test_maintenance_scope_never_crosses_installation_channel_or_household`, `tests/backend/test_recurrence_http.py::test_protected_review_preview_apply_and_original_receipt` |
| recurrence-execution-C45 | Witness | `tests/backend/test_sqlite_recurrence.py::test_normal_transactions_refuse_schema7_until_explicit_atomic_upgrade`, `tests/containers/test_app_compatibility.py` |
| recurrence-execution-C46 | Witness | `tests/backend/test_sqlite_recurrence_integrity.py::test_schema7_ddl_failure_rolls_back_tables_version_and_original_business_records`, `tests/backend/test_recurrence_lifecycle_migration.py::test_relabelled_schema9_with_an_unrecognized_layout_is_refused` |
| recurrence-execution-C47 | Witness | `tests/backend/test_fixed_materialization.py::test_actual_restore_retains_absent_slot_proof_and_step_never_recreates_it` |
| recurrence-execution-C48 | Witness | `tests/containers/test_app_compatibility.py`, `tests/containers/test_administration_image.py` |
| recurrence-execution-C49 | Witness | `tests/backend/test_recurrence_runtime.py::test_both_business_runtimes_start_only_during_lifespan_and_resume_after_restart`, `tests/backend/test_recurrence_runtime.py::test_both_owned_lifetimes_resume_a_relative_cycle_after_bootstrap` |
| recurrence-execution-C50 | Witness | `tests/backend/test_recurrence_worker.py::test_unconfirmed_tick_is_reported_safely_and_a_later_poll_can_recover`, `tests/backend/test_fair_recurrence.py::test_one_unavailable_rule_does_not_starve_the_other_selected_rule` |
| recurrence-execution-C51 | Witness | `tests/containers/test_app_image.py::test_calendar_core_uses_both_exact_packaged_compositions`, `tests/containers/test_app_compatibility.py` |
| recurrence-execution-C52 | Witness | `tests/architecture/test_python_architecture.py`, `tests/python/test_backend_coverage.py` |

## Storage continuation

See the [owning specification](../../specs/recurrence-storage-continuation.md).

| Case | Evidence status | Automated witness or remaining assertion |
| --- | --- | --- |
| recurrence-storage-C01 | Partial | `tests/backend/test_fixed_batch_review.py::test_complete_plan_byte_bounds_and_mismatched_write_snapshot_fail_closed`, `tests/backend/test_recurrence_canonical_storage.py`. Verify the exact canonical 65,536-byte cutoff and that bounded execution never builds a single oversized batch receipt. |
| recurrence-storage-C02 | Witness | `tests/backend/test_recurrence_canonical_storage.py::test_actual_noncanonical_storage_is_not_repaired_by_read_or_checkpoint`, `tests/backend/test_sqlite_recurrence_integrity.py::test_header_body_mismatch_is_rejected_by_independent_repository_and_checkpoint` |
| recurrence-storage-C03 | Witness | `tests/backend/test_sqlite_recurrence.py::test_normal_transactions_refuse_schema7_until_explicit_atomic_upgrade` |
| recurrence-storage-C04 | Witness | `tests/backend/test_sqlite_recurrence.py::test_slot_identity_is_unique_and_requires_its_exact_task_and_receipt`, `tests/backend/test_sqlite_recurrence_integrity.py::test_semantic_probe_rejects_missing_source_binding_or_original_effect` |

## Lifecycle refinements

See the [owning specification](../../specs/recurrence-lifecycle-calendar.md).

| Case | Evidence status | Automated witness or remaining assertion |
| --- | --- | --- |
| recurrence-lifecycle-calendar-C19 | Witness | `tests/backend/test_relative_materialization.py::test_actual_restore_retains_initial_proof_without_recreating_absent_work` |
| recurrence-lifecycle-calendar-C20 | Witness | `tests/backend/test_recurrence_review.py::test_concurrent_start_requires_review_refresh_and_never_creates_a_second_initial` |
| recurrence-lifecycle-calendar-C21 | Witness | `tests/backend/test_recurrence_qualification.py::test_nonactionable_final_scan_unit_keeps_the_next_source_for_a_fresh_runner` |
| recurrence-lifecycle-calendar-C22 | Witness | `tests/backend/test_recurrence_source_observations.py::test_original_snapshots_are_bounded_ordered_and_independent_of_delivery`, `tests/backend/test_recurrence_source_observations.py::test_composition_scope_cannot_cross_installation_channel_or_household`, `tests/backend/test_relative_lifecycle_consumer.py::test_restore_of_later_completion_fences_an_absent_original_without_generating` |
| recurrence-lifecycle-calendar-C23 | Witness | `tests/backend/test_recurrence_qualification.py::test_delayed_approval_after_a_reviewed_rule_edit_and_restore_cannot_grant_again` |
| recurrence-lifecycle-calendar-C24 | Partial | `tests/backend/test_recurrence_qualification.py::test_a_committing_start_wins_against_an_independent_invalidation_writer`, `tests/backend/test_relative_lifecycle_consumer.py::test_restore_retains_a_downstream_start_even_if_current_work_looks_unstarted`. Independent SQLite writers and compatible restoration preserve downstream work. Ledger compensation requires the owning consumers. |
| recurrence-lifecycle-calendar-C25 | Witness | `tests/backend/test_mixed_recurrence.py::test_mixed_rules_share_one_slot_limit_and_restart_the_same_frontier`, `tests/backend/test_mixed_recurrence.py::test_relative_bootstrap_replay_charges_the_shared_slot_budget`, `tests/backend/test_fair_recurrence.py::test_actual_global_thousand_slot_limit_retains_the_next_obligation_for_another_tick` |
| recurrence-lifecycle-calendar-C26 | Witness | `tests/backend/test_fair_recurrence.py::test_repeated_restart_after_every_first_step_cannot_starve_the_other_ninety_eight_rules`, `tests/backend/test_mixed_recurrence.py::test_unavailable_source_scan_leaves_fixed_and_relative_initial_work_fair` |
| recurrence-lifecycle-calendar-C27 | Witness | `tests/backend/test_recurrence_qualification.py::test_batch_review_binds_excluded_moved_and_concurrently_started_work`, `frontend/tests/e2e/tasks.spec.ts` (protected calendar and fixed batch review). Independent SQLite writers invalidate the stale plan; exact recovery preserves the accepted command and work history. |
| recurrence-lifecycle-calendar-C28 | Witness | `tests/backend/test_fixed_batch_review.py::test_complete_plan_byte_bounds_and_mismatched_write_snapshot_fail_closed` |
| recurrence-lifecycle-calendar-C29 | Gap | `tests/backend/test_calendar_queries.py::test_combined_filters_count_actual_performers_independently_of_assignees`. Current category labels come from tags. Audit the combined category-reference and distinct-occurrence query after that contract is implemented. |
| recurrence-lifecycle-calendar-C30 | Witness | `tests/backend/test_recurrence_qualification.py::test_calendar_stays_pending_when_the_watermark_has_passed_unresolved_work` |
| recurrence-lifecycle-calendar-C31 | Witness | `tests/backend/test_calendar_http.py::test_owner_calendar_preferences_are_private_and_recover_exact_int64`, `tests/backend/test_calendar_boundaries.py::test_an_outage_lease_does_not_authorize_another_members_cursor`. Both compositions reject another administrator’s private result or cursor. Outage reads leave SQLite bytes unchanged and the original lease expires on time. |
| recurrence-lifecycle-calendar-C32 | Witness | `frontend/tests/e2e/workspace-navigation.spec.ts`, `frontend/tests/recurrence-review.test.ts`. The exact browser mutation and original response preserve the SQLite revision above 2^53. Both unrelated journals reject recurrence bytes, including a forged namespace. |
| recurrence-lifecycle-calendar-C33 | Witness | `tests/backend/test_recurrence_lifecycle_migration.py::test_supported_schema9_keeps_fixed_work_pristine_relative_progress_and_private_choices`, `tests/backend/test_recurrence_lifecycle_migration.py::test_late_lifecycle_ddl_failure_leaves_genuine_schema9_bytes_untouched` |
| recurrence-lifecycle-calendar-C34 | Partial | `tests/backend/test_relative_lifecycle_consumer.py::test_compatible_restore_copies_later_cycle_proof_without_the_successor`, `tests/containers/test_administration_image.py`. Current restore and old-image refusal run. Keep the original schema-10 pairing distinct from schema-14 packaging evidence. |
| recurrence-lifecycle-calendar-C35 | Witness | `frontend/tests/e2e/tasks.spec.ts` (protected calendar and fixed batch review in native and standalone, EN and ES). At 320 px, keyboard navigation changes from Month to Agenda. Real stored entries distinguish all four time roles and independent pending processing. The review reason and task title remain literal text. |
| recurrence-lifecycle-calendar-C36 | Witness | `tests/ha/calendar_smoke.py`, `tests/backend/test_ha_calendar_projection.py::test_ha_projection_keeps_uids_offsets_and_date_only_markers_through_retry` |
| recurrence-lifecycle-calendar-C37 | Witness | `tests/backend/test_relative_lifecycle.py::test_c37_outcome_preserves_original_receipt_meaning_and_rejects_mixed_valid_fields` |
| recurrence-lifecycle-calendar-C38 | Witness | `tests/backend/test_relative_lifecycle_consumer.py::test_c38_mismatched_persisted_outcome_fails_without_effects_or_repair` |
| recurrence-lifecycle-calendar-C39 | Witness | `tests/backend/test_recurrence_lifecycle_migration.py::test_genuine_schema11_horizon_migration_preserves_private_preferences_and_history`, `tests/backend/test_recurrence_runtime.py::test_saved_household_horizon_limits_next_worker_run_in_both_compositions` |

## Native Home Assistant calendar

See the [owning specification](../../specs/home-assistant-calendar.md).

| Case | Evidence status | Automated witness or remaining assertion |
| --- | --- | --- |
| domus-native-calendar-C01 | Witness | `tests/ha/calendar_smoke.py`, `tests/containers/test_app_image.py::test_calendar_core_uses_both_exact_packaged_compositions` |
| domus-native-calendar-C02 | Witness | `tests/ha/calendar_smoke.py`, `tests/backend/test_ha_calendar_installation.py::test_calendar_bearer_is_only_for_its_scoped_read_and_rotates` |
| domus-native-calendar-C03 | Witness | `tests/backend/test_ha_calendar_installation.py::test_calendar_bearer_is_only_for_its_scoped_read_and_rotates`, `tests/containers/test_app_image.py::test_calendar_core_uses_both_exact_packaged_compositions` |
| domus-native-calendar-C04 | Witness | `tests/ha/calendar_smoke.py`, `tests/backend/test_ha_calendar_projection.py::test_ha_projection_keeps_uids_offsets_and_date_only_markers_through_retry` |
| domus-native-calendar-C05 | Witness | `tests/ha/calendar_smoke.py`, `tests/containers/test_app_image.py::test_calendar_core_read_lifecycle_and_configuration` |
| domus-native-calendar-C06 | Witness | `tests/ha/calendar_smoke.py`, `tests/containers/test_app_image.py::test_calendar_core_read_lifecycle_and_configuration` |
| domus-native-calendar-C07 | Witness | `tests/backend/test_ha_calendar_installation.py::test_calendar_bearer_is_only_for_its_scoped_read_and_rotates` |

## Retained integration aliases

The original links below remain required. An alias inherits the state of all its mapped cases.

| Alias | Owning cases |
| --- | --- |
| recurrence-storage-continuation-C01 | recurrence-execution-C45, recurrence-execution-C46 |
| recurrence-storage-continuation-C02 | recurrence-execution-C17, recurrence-execution-C18, recurrence-execution-C19 |
| recurrence-storage-continuation-C03 | recurrence-execution-C21, recurrence-execution-C31, recurrence-execution-C32, recurrence-execution-C35 |
| recurrence-storage-continuation-C04 | recurrence-execution-C37, recurrence-execution-C38, recurrence-execution-C39, recurrence-execution-C43 |
| recurrence-lifecycle-calendar-C01 | recurrence-execution-C06 |
| recurrence-lifecycle-calendar-C02 | recurrence-execution-C07, recurrence-execution-C32 |
| recurrence-lifecycle-calendar-C03 | recurrence-execution-C29, recurrence-calendar-C12, recurrence-calendar-C25 |
| recurrence-lifecycle-calendar-C04 | recurrence-execution-C21, recurrence-execution-C33, recurrence-calendar-C29, recurrence-calendar-C30 |
| recurrence-lifecycle-calendar-C05 | recurrence-execution-C24, recurrence-execution-C28 |
| recurrence-lifecycle-calendar-C06 | recurrence-execution-C28, recurrence-execution-C30 |
| recurrence-lifecycle-calendar-C07 | recurrence-execution-C17, recurrence-execution-C18, recurrence-execution-C19 |
| recurrence-lifecycle-calendar-C08 | recurrence-execution-C26 |
| recurrence-lifecycle-calendar-C09 | recurrence-execution-C27 |
| recurrence-lifecycle-calendar-C10 | recurrence-execution-C34, recurrence-execution-C43 |
| recurrence-lifecycle-calendar-C11 | recurrence-execution-C16, recurrence-execution-C23 |
| recurrence-lifecycle-calendar-C12 | recurrence-execution-C16, recurrence-execution-C23, recurrence-lifecycle-calendar-C21 |
| recurrence-lifecycle-calendar-C13 | recurrence-execution-C20, recurrence-execution-C31, recurrence-execution-C32, recurrence-execution-C36 |
| recurrence-lifecycle-calendar-C14 | recurrence-execution-C20, recurrence-execution-C28, recurrence-execution-C30, recurrence-lifecycle-calendar-C22 |
| recurrence-lifecycle-calendar-C15 | recurrence-execution-C37, recurrence-execution-C38, recurrence-execution-C39, recurrence-execution-C40, recurrence-execution-C41, recurrence-execution-C42 |
| recurrence-lifecycle-calendar-C16 | recurrence-execution-C22, recurrence-execution-C45, recurrence-execution-C46, recurrence-execution-C48, recurrence-execution-C49, recurrence-lifecycle-calendar-C33 |
| recurrence-lifecycle-calendar-C17 | recurrence-calendar-C16, recurrence-calendar-C17, recurrence-calendar-C18, recurrence-lifecycle-calendar-C35 |
| recurrence-lifecycle-calendar-C18 | recurrence-execution-C38, recurrence-execution-C43, recurrence-execution-C44, recurrence-lifecycle-calendar-C31, recurrence-lifecycle-calendar-C32 |

## Candidate package and isolated execution

The private qualification recipe uses `0.0.0-qualification.1`, source
`449dc04c17a9c41d949d74cd341bf1e943a2fba9`, and the codeload archive digest
`dd7f4cf74a37576af56d4e7b9ad99545b9506de6517b582f7cdf17030e85d69f`.
It uses the pinned [Supervisor Dockerfile](../../addon-edge/Dockerfile) with the
candidate commit, archive digest, version and channel set explicitly. The
[qualification schema overlay](../../tests/fixtures/current-app/supervisor-calendar-options.yaml)
adds an optional calendar digest without a default. The channel slugs are
`domus` and `domus_edge`. Both use Ingress port 8099 and an empty port mapping.

The following gates remain distinct:

| Gate | Evidence |
| --- | --- |
| Current source | The baseline develop CI passed. The qualification PR runs the expanded acceptance on both CI architectures. |
| Local package builds | Stable and Edge built from the pinned archive on amd64 and ARM64. Each image recorded the same source revision. |
| Owned runtime | The isolated test launched each channel through the packaged HA launcher and standalone owned runtime. Core registered four separate entities, rejected a bearer from the other channel, and returned a real materialized date-only schedule and a timed deadline. The test verifies the absence of host port mappings. |
| Credential and recovery | Core fixture coverage exercises rotation, wrong source identity, TLS verification, response limits, retries, pending projection and unload. The calendar HTTP regression exercises local permission changes during an HA outage and denial at the original lease deadline. |
| Compatible data rollback | Existing exact-image refusal and restoration suites run on both architectures. Qualify the final candidate with a disposable copy of the supported old data before owner acceptance. |
| Owner acceptance | Exercise a candidate in the owner's Home Assistant with an authorized backup and rollback. Record the exact HA/Core/Supervisor versions, package SHA, localized browser journeys and cleanup. |
| Stable and Edge distribution | Use an explicitly authorized packaging and distribution step after the recurrence cases and applicable release gates pass. |

For a local rerun of the package test, build the reviewed images with separate
tags. Supply the Edge tag as `DOMUS_TEST_IMAGE` and the Stable tag as
`DOMUS_TEST_STABLE_IMAGE`, then run:

```text
uv run pytest tests/containers/test_app_image.py -k calendar --no-cov
```

The default CI test uses the checked-out image and invokes each channel with
its actual entrypoint on an independent private directory. Stable and Edge in
this test are scoped installations. Distribution and live Supervisor acceptance
require their own evidence.
