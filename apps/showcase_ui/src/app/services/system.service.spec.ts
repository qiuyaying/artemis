import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { SystemReadinessReport } from '../core/models/system.model';
import { SystemService } from './system.service';

describe('SystemService readiness polling', () => {
  let service: SystemService;
  let http: HttpTestingController;

  const report = (timestamp: number): SystemReadinessReport => ({
    overall_ready: true,
    blocker_count: 3,
    passed_blocker_count: 3,
    probes: [],
    active_device: null,
    os_type: 'windows',
    timestamp
  });

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        SystemService,
        provideHttpClient(withXhr()),
        provideHttpClientTesting()
      ]
    });
    service = TestBed.inject(SystemService);
    http = TestBed.inject(HttpTestingController);
    service.stopAutoPolling();
    http.expectOne("/api/ios/status").flush({platform: "android", ready: false, target: null});
  });

  afterEach(() => http.verify());

  it('restores the saved iPhone on Android to iOS switch', () => {
    service.iosStatus.set({platform: 'android', ready: false, target: {device_id: 'phone', wda_url: 'http://127.0.0.1:8101'}});
    service.selectPlatform('ios');
    http.expectOne('/api/ios/devices').flush({devices: []});
    expect(service.iosBusy()).toBeTrue();
    expect(service.isDeviceReady()).toBeFalse();
    const request = http.expectOne('/api/ios/select');
    expect(request.request.body).toEqual({platform: 'ios', device_id: 'phone', wda_url: 'http://127.0.0.1:8101'});
    request.flush({platform: 'ios', ready: true, target: {device_id: 'phone'}});
    expect(service.isDeviceReady()).toBeTrue();
    expect(service.iosBusy()).toBeFalse();
  });

  it('does not overwrite a new selection with an older status response', () => {
    service.refreshIosStatus();
    const stale = http.expectOne('/api/ios/status');
    service.connectIos('phone', 'http://127.0.0.1:8101');
    http.expectOne('/api/ios/select').flush({platform: 'ios', ready: true, target: {device_id: 'phone'}});
    stale.flush({platform: 'android', ready: false});
    expect(service.platform()).toBe('ios');
    expect(service.isDeviceReady()).toBeTrue();
  });

  it('uses WDA readiness for iOS without requiring Android tools', () => {
    service.platform.set('ios');
    service.iosStatus.set({platform: 'ios', ready: true, target: {device_id: 'phone'}});
    service.readinessReport.set({...report(1), probes: [
      {id: 'python_runtime', status: 'pass'}, {id: 'system_config', status: 'pass'},
      {id: 'llm_api_key', status: 'pass'}, {id: 'android_adb', status: 'fail', metadata: {installed: false}},
      {id: 'toolchain', status: 'fail'}
    ] as any});
    expect(service.isReady()).toBeTrue();
    service.iosStatus.set({platform: 'ios', ready: false});
    expect(service.isReady()).toBeFalse();
    service.platform.set('android');
    expect(service.isReady()).toBeFalse();
  });

  it('shares one HTTP request across overlapping readiness callers', () => {
    let firstTimestamp = 0;
    let secondTimestamp = 0;

    service.fetchReadiness().subscribe(value => firstTimestamp = value.timestamp);
    service.fetchReadiness(true).subscribe(value => secondTimestamp = value.timestamp);

    const request = http.expectOne('/api/system/readiness');
    request.flush(report(10));

    expect(firstTimestamp).toBe(10);
    expect(secondTimestamp).toBe(10);
    expect(service.readinessReport()?.timestamp).toBe(10);
    expect(service.isLoading()).toBeFalse();
  });

  it('does not let an older snapshot replace a newer report', () => {
    service.fetchReadiness().subscribe();
    http.expectOne('/api/system/readiness').flush(report(20));

    service.fetchReadiness().subscribe();
    http.expectOne('/api/system/readiness').flush(report(10));

    expect(service.readinessReport()?.timestamp).toBe(20);
  });

  it('requests a forced backend refresh for a manual re-check', () => {
    service.fetchReadiness(false, true).subscribe();

    const request = http.expectOne(req =>
      req.url === '/api/system/readiness' && req.params.get('force') === 'true'
    );
    expect(request.request.params.get('force')).toBe('true');
    request.flush(report(30));
  });

  it('loads the active ADB server endpoint', () => {
    service.fetchAdbServerStatus().subscribe();

    const request = http.expectOne('/api/system/adb/server');
    request.flush({
      endpoint: {
        host: '127.0.0.1',
        port: 5038,
        socket: 'tcp:127.0.0.1:5038',
        mode: 'remote',
        is_local_default: false
      }
    });

    expect(service.isRemoteAdbServer()).toBeTrue();
    expect(service.adbServerStatus()?.endpoint.port).toBe(5038);
  });

  it('activates an ADB server endpoint and applies its readiness report', () => {
    service.connectAdbServer('127.0.0.1', 5038, true).subscribe();

    const request = http.expectOne('/api/system/adb/server/connect');
    expect(request.request.body).toEqual({
      host: '127.0.0.1',
      port: 5038,
      persist: true
    });
    request.flush({
      connection_result: {
        success: true,
        message: 'Connected.',
        endpoint: {
          host: '127.0.0.1',
          port: 5038,
          socket: 'tcp:127.0.0.1:5038',
          mode: 'remote',
          is_local_default: false
        },
        devices: []
      },
      report: report(40)
    });

    expect(service.isRemoteAdbServer()).toBeTrue();
    expect(service.readinessReport()?.timestamp).toBe(40);
  });

  it('probes an ADB server without changing the active endpoint', () => {
    service.probeAdbServer('127.0.0.1', 5038).subscribe();

    const request = http.expectOne('/api/system/adb/server/probe');
    expect(request.request.body).toEqual({
      host: '127.0.0.1',
      port: 5038,
      persist: false
    });
    request.flush({
      connection_result: {
        success: true,
        message: 'Endpoint is reachable.',
        endpoint: {
          host: '127.0.0.1',
          port: 5038,
          socket: 'tcp:127.0.0.1:5038',
          identity: 'tcp:127.0.0.1:5038',
          mode: 'remote',
          is_local_default: false
        },
        devices: []
      }
    });

    expect(service.adbServerStatus()).toBeNull();
  });

  it('restores the standard local ADB server explicitly', () => {
    service.useLocalAdbServer(true).subscribe();

    const request = http.expectOne(req =>
      req.url === '/api/system/adb/server/local' && req.params.get('persist') === 'true'
    );
    request.flush({
      connection_result: {
        success: true,
        message: 'Using local ADB.',
        endpoint: {
          host: '127.0.0.1',
          port: 5037,
          socket: 'tcp:127.0.0.1:5037',
          mode: 'local',
          is_local_default: true
        },
        devices: []
      },
      report: report(50)
    });

    expect(service.isRemoteAdbServer()).toBeFalse();
    expect(service.adbServerStatus()?.endpoint.port).toBe(5037);
  });
});
