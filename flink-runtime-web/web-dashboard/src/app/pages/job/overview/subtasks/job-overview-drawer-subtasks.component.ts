/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { ChangeDetectionStrategy, ChangeDetectorRef, Component, Inject, OnDestroy, OnInit, Type } from '@angular/core';
import { of, Subject } from 'rxjs';
import { catchError, mergeMap, takeUntil } from 'rxjs/operators';

import {
  JobVertexAggregated,
  JobVertexStatus,
  JobVertexStatusDuration,
  JobVertexSubTask
} from '@flink-runtime-web/interfaces';
import {
  JOB_OVERVIEW_MODULE_CONFIG,
  JOB_OVERVIEW_MODULE_DEFAULT_CONFIG,
  JobOverviewModuleConfig
} from '@flink-runtime-web/pages/job/overview/job-overview.config';
import { JobService } from '@flink-runtime-web/services';
import { typeDefinition } from '@flink-runtime-web/utils/strong-type';
import { NzTableSortFn } from 'ng-zorro-antd/table/src/table.types';

import { JobLocalService } from '../../job-local.service';

function createSortFn(selector: (item: JobVertexSubTask) => number | string): NzTableSortFn<JobVertexSubTask> {
  return (pre, next) => (selector(pre) > selector(next) ? 1 : -1);
}

@Component({
  selector: 'flink-job-overview-drawer-subtasks',
  templateUrl: './job-overview-drawer-subtasks.component.html',
  styleUrls: ['./job-overview-drawer-subtasks.component.less'],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class JobOverviewDrawerSubtasksComponent implements OnInit, OnDestroy {
  readonly trackBySubtask = (_: number, node: JobVertexSubTask): number => node.subtask;

  readonly sortReadBytesFn = createSortFn(item => item.metrics?.['read-bytes']);
  readonly sortReadRecordsFn = createSortFn(item => item.metrics?.['read-records']);
  readonly sortWriteBytesFn = createSortFn(item => item.metrics?.['write-bytes']);
  readonly sortWriteRecordsFn = createSortFn(item => item.metrics?.['write-records']);
  readonly sortAttemptFn = createSortFn(item => item.attempt);
  readonly sortHostFn = createSortFn(item => item.host);
  readonly sortStartTimeFn = createSortFn(item => item['start_time']);
  readonly sortDurationFn = createSortFn(item => item.duration);
  readonly sortEndTimeFn = createSortFn(item => item['end-time']);
  readonly sortStatusFn = createSortFn(item => item.status);

  listOfTask: JobVertexSubTask[] = [];
  aggregated?: JobVertexAggregated;
  isLoading = true;
  virtualItemSize = 36;
  actionComponent: Type<unknown>;
  durationBadgeComponent: Type<unknown>;
  stateBadgeComponent: Type<unknown>;
  readonly narrowLogData = typeDefinition<JobVertexSubTask>();

  private readonly destroy$ = new Subject<void>();

  constructor(
    private readonly jobService: JobService,
    private readonly jobLocalService: JobLocalService,
    private readonly cdr: ChangeDetectorRef,
    @Inject(JOB_OVERVIEW_MODULE_CONFIG) readonly moduleConfig: JobOverviewModuleConfig
  ) {
    this.actionComponent =
      moduleConfig.customComponents?.subtaskActionComponent ||
      JOB_OVERVIEW_MODULE_DEFAULT_CONFIG.customComponents.subtaskActionComponent;
    this.durationBadgeComponent =
      moduleConfig.customComponents?.durationBadgeComponent ||
      JOB_OVERVIEW_MODULE_DEFAULT_CONFIG.customComponents.durationBadgeComponent;
    this.stateBadgeComponent =
      moduleConfig.customComponents?.stateBadgeComponent ||
      JOB_OVERVIEW_MODULE_DEFAULT_CONFIG.customComponents.stateBadgeComponent;
  }

  ngOnInit(): void {
    this.jobLocalService
      .jobWithVertexChanges()
      .pipe(
        mergeMap(data =>
          this.jobService.loadSubTasks(data.job.jid, data.vertex!.id).pipe(catchError(() => of(undefined)))
        ),
        takeUntil(this.destroy$)
      )
      .subscribe(data => {
        this.listOfTask = data?.subtasks || [];
        this.aggregated = data?.aggregated;
        this.isLoading = false;
        this.cdr.markForCheck();
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  convertStatusDuration(statusDuration: JobVertexStatusDuration<number>): Array<{ state: string; duration: number }> {
    const orderedKeys = [
      JobVertexStatus.CREATED,
      JobVertexStatus.SCHEDULED,
      JobVertexStatus.DEPLOYING,
      JobVertexStatus.INITIALIZING,
      JobVertexStatus.RUNNING
    ];

    return orderedKeys.map(key => ({ state: key, duration: statusDuration[key] }));
  }
}
