import datetime

from flask import Blueprint

from lib.utils import jsonify

health_checks = Blueprint('health-check', __name__)


@health_checks.route("", methods=["GET"])
def health_check():
    start = datetime.datetime.now()
    total, success, entries, unhealthy = do_subservice_checks()

    if total == success:
        status = "Healthy"
    elif unhealthy:
        status = "Unhealthy"
    else:
        status = "Degraded"

    end = datetime.datetime.now()
    duration = str(end - start)
    data = {
        "status": status,
        "totalDuration": duration,
        "entries": entries
    }
    return jsonify(data)


def do_subservice_checks():
    unhealthy = False
    total = len(CHECKS)
    successes = 0
    entries = {}

    for subservice, check_func in CHECKS.items():
        start = datetime.datetime.now()
        data, status, critical = check_func()
        end = datetime.datetime.now()
        duration = str(end - start)
        entries[subservice] = {
            "data": data,
            "duration": duration,
            "status": status
        }
        if critical:
            unhealthy = True
        elif status == "Healthy":
            successes += 1

    return total, successes, entries, unhealthy


# ===== Subservices =====
# should return a 3-tuple of (data, status, critical)
# where data is a dict, status is "Healthy", "Degraded", or "Unhealthy",
# and critical is a bool saying whether to mark the entire service as unhealthy
def check_mongo():
    return {}, "Healthy", True


def check_redis():
    return {}, "Healthy", False


def check_discord():
    return {}, "Healthy", False


# ===== Check Defn =====
CHECKS = {
    "mongoDB": check_mongo,
    "Redis": check_redis,
    "Discord API": check_discord
}
