from models.connection import DBConnection
from utils.types import OrgType, RolesType
from decouple import config as decouple_config

db = DBConnection()


def fetch_queries(muid):
    query = """
        SELECT
            user.id,
            user.muid,
            user.full_name,
            role.title AS role,
            wallet.karma,
            interest_group.name AS interest_group_name,
            socials.github,
            organization.code AS organization_code,
            organization.org_type AS org_type
        FROM
            user
        LEFT JOIN wallet ON user.id = wallet.user_id
        LEFT JOIN user_ig_link ON user.id = user_ig_link.user_id
        LEFT JOIN interest_group ON user_ig_link.ig_id = interest_group.id
        LEFT JOIN user_role_link ON user_role_link.user_id = user.id
        LEFT JOIN role ON role.id = user_role_link.role_id
        LEFT JOIN socials ON user.id = socials.user_id
        LEFT JOIN user_organization_link ON user.id = user_organization_link.user_id
        LEFT JOIN organization ON user_organization_link.org_id = organization.id and org_type = :org_type
        WHERE user.muid = :muid;
    """
    user_data = db.fetch_all_data(
        query, params={"muid": muid, "org_type": OrgType.COLLEGE.value}
    )

    if user_data:
        data = {
            "muid": f"{user_data[0][1]}",
            "name": f"{user_data[0][2]}",
            "profile_pic": f"{decouple_config("BASE_URL")/{user_data[0][0]}.png}",
            "karma": str(user_data[0][4]),
            "github_username": user_data[0][6],
            "org_code": list(set([row[7] for row in user_data if row[7]])),
            "roles": list(set([row[3] for row in user_data if row[3]])),
            "ig_name": list(set([row[5] for row in user_data if row[5]])),
            "org_types": list(set([row[8] for row in user_data if row[8]])),
        }
    else:
        return None

    main_role = next(
        (
            role
            for role in data["roles"]
            if role
            in [
                RolesType.STUDENT.value,
                RolesType.MENTOR.value,
                RolesType.ENABLER.value,
            ]
        ),
        RolesType.MULEARNER.value,
    )

    if main_role in [RolesType.MENTOR.value, RolesType.ENABLER.value]:
        rank_query = """
            SELECT wallet.karma, user.muid
            FROM wallet
            INNER JOIN user_role_link ON user_role_link.user_id = wallet.user_id
            INNER JOIN role ON role.id = user_role_link.role_id
            INNER JOIN user ON user.id = wallet.user_id
            WHERE role.title = :title
            ORDER BY wallet.karma DESC;

        """
        params = {"title": main_role}
    else:
        rank_query = """
            SELECT wallet.karma, user.muid
            FROM wallet
            LEFT JOIN (
                SELECT user_role_link.user_id
                FROM user_role_link
                INNER JOIN role ON role.id = user_role_link.role_id
                GROUP BY user_role_link.user_id
                HAVING SUM(IF(role.title IN (:mentor, :enabler), 1, 0)) = 0
            ) AS users ON wallet.user_id = users.user_id
            INNER JOIN user ON wallet.user_id = user.id
            ORDER BY wallet.karma DESC;

        """
        params = {"enabler": RolesType.ENABLER.value, "mentor": RolesType.MENTOR.value}

    rank_list = db.fetch_all_data(rank_query, params)

    count = 0
    for x in rank_list:
        count += 1
        if x[1] == data["muid"]:
            data["rank"] = count
            data["score"] = int(x[0])
            data["main_role"] = main_role

    return data
