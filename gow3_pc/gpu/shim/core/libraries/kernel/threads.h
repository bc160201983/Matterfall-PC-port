// gow3: host threads that may call guest code (AvPlayer allocator callbacks).
// Each thread gets a guest TCB (GS base, TLS) from the C runtime before running.
#pragma once
#include <atomic>
#include <chrono>
#include <cstdio>
#include <functional>
#include <memory>
#include <mutex>
#include <stop_token>
#include <system_error>
#include <thread>
#include "common/types.h"

extern "C" void runtime_thread_attach_host(const char* name);

namespace Libraries::Kernel {
class Thread {
public:
    Thread() = default;
    ~Thread() { Stop(); }
    void Run(std::function<void(std::stop_token)>&& func) {
        std::lock_guard lock{mutex};
        finished = std::make_shared<std::atomic<bool>>(false);
        thread = std::jthread([func = std::move(func), done = finished](std::stop_token stop) {
            runtime_thread_attach_host("gow3:hle");
            func(stop);
            done->store(true);
        });
        id = thread.get_id();
        stop_source = thread.get_stop_source();
    }
    // A thread may stop its own Thread object (AvPlayer does); it detaches instead of joining.
    // gow3 30 Oct 2026: AvPlayer's decoder threads end by joining themselves while the demuxer
    // thread joins them too: two threads used one std::jthread at once, the detach closed the
    // handle the join was waiting on, and the join failed ("HLE thread: join failed ... No such
    // device or address" in every movie). The thread is now taken out of the object under a
    // lock by whichever caller comes first; a later caller waits for the function to return.
    // These are called from guest code, which a C++ exception cannot unwind: a failed join is
    // still logged and the thread detached instead.
    void Join() {
        std::jthread mine;
        std::shared_ptr<std::atomic<bool>> done;
        bool self;
        {
            std::lock_guard lock{mutex};
            done = finished;
            self = id == std::this_thread::get_id();
            if (thread.joinable()) {
                mine = std::move(thread);
            }
        }
        if (!mine.joinable()) {
            if (!self) WaitFinished(done); // the thread itself or another caller let it go first
            return;
        }
        if (self) {
            mine.detach();
            return;
        }
        try {
            mine.join();
        } catch (const std::system_error& error) {
            std::fprintf(stderr, "HLE thread: join failed (%s); waiting for it to finish\n",
                         error.what());
            WaitFinished(done);
            if (mine.joinable()) mine.detach();
        }
    }
    // Still running (or not yet joined), also while another caller is joining it.
    bool Joinable() const {
        std::lock_guard lock{mutex};
        return thread.joinable() || (finished && !finished->load());
    }
    // The stop request goes through a copy of the thread's stop source: another caller may have
    // taken the thread out of this object to join it (AvPlayer's demuxer joins the decoders),
    // and that join only ends once the thread is told to stop.
    void Stop() {
        {
            std::lock_guard lock{mutex};
            if (!finished) return; // never started
            stop_source.request_stop();
        }
        Join();
    }

private:
    // Waits (at most 5 s) until the thread's function has returned.
    static void WaitFinished(const std::shared_ptr<std::atomic<bool>>& done) {
        if (!done) return;
        for (int waited = 0; !done->load() && waited < 5000; ++waited) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }

    mutable std::mutex mutex;
    std::jthread thread;
    std::thread::id id;
    std::stop_source stop_source{std::nostopstate};
    std::shared_ptr<std::atomic<bool>> finished;
};
} // namespace Libraries::Kernel
