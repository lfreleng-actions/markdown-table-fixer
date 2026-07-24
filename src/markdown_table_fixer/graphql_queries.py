# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""GraphQL queries for efficient organization scanning."""

# Mirrors dependamerge's repo enumeration query so organization counts stay
# consistent; excludes PR nodes to keep the response small.
ORG_REPOS_ONLY = """
query($org: String!, $reposCursor: String) {
  organization(login: $org) {
    repositories(first: 100, after: $reposCursor, orderBy: { field: NAME, direction: ASC }) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        nameWithOwner
        isArchived
      }
    }
  }
}
"""


# Query to get repositories WITH open PRs in an organization (aggregated)
# NOTE: This should NOT be used for counting - use ORG_REPOS_ONLY instead
ORG_REPOS_WITH_PRS = """
query($org: String!, $cursor: String, $prsPageSize: Int!, $contextsPageSize: Int!) {
  organization(login: $org) {
    repositories(first: 30, after: $cursor, orderBy: { field: NAME, direction: ASC }) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        nameWithOwner
        isArchived
        owner {
          login
        }
        name
        pullRequests(
          states: OPEN
          first: $prsPageSize
          orderBy: { field: CREATED_AT, direction: DESC }
        ) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            number
            title
            body
            url
            isDraft
            author { login }
            mergeable
            mergeStateStatus
            baseRefName
            headRefName
            headRefOid
            createdAt
            updatedAt
            headRepository {
              nameWithOwner
              url
            }
            baseRepository {
              nameWithOwner
              url
            }
            isCrossRepository
            maintainerCanModify
            commits(last: 1) {
              nodes {
                commit {
                  oid
                  statusCheckRollup {
                    state
                    contexts(first: $contextsPageSize) {
                      nodes {
                        __typename
                        ... on CheckRun {
                          name
                          status
                          conclusion
                        }
                        ... on StatusContext {
                          context
                          state
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


# Query to get open PRs for a specific repository with status checks
# This matches dependamerge's REPO_OPEN_PRS_PAGE with parameterized page sizes
REPO_OPEN_PRS_PAGE = """
query($owner: String!, $name: String!, $prsCursor: String, $prsPageSize: Int!, $filesPageSize: Int!, $commentsPageSize: Int!, $contextsPageSize: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    pullRequests(
      states: OPEN
      first: $prsPageSize
      after: $prsCursor
      orderBy: { field: CREATED_AT, direction: DESC }
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        title
        body
        url
        isDraft
        author { login }
        mergeable
        mergeStateStatus
        baseRefName
        headRefName
        headRefOid
        createdAt
        updatedAt
        files(first: $filesPageSize) {
          nodes {
            path
            additions
            deletions
          }
        }
        comments(first: $commentsPageSize, orderBy: { field: UPDATED_AT, direction: DESC }) {
          nodes {
            author { login }
            body
            createdAt
          }
        }
        reviews(first: 20, states: [PENDING, COMMENTED, APPROVED, CHANGES_REQUESTED]) {
          nodes {
            id
            author { login }
            state
            body
            createdAt
            updatedAt
          }
        }
        headRepository {
          nameWithOwner
          url
        }
        baseRepository {
          nameWithOwner
          url
        }
        isCrossRepository
        maintainerCanModify
        commits(last: 1) {
          nodes {
            commit {
              oid
              statusCheckRollup {
                state
                contexts(first: $contextsPageSize) {
                  nodes {
                    __typename
                    ... on CheckRun {
                      name
                      status
                      conclusion
                    }
                    ... on StatusContext {
                      context
                      state
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# Query to get a single PR with status checks
PR_WITH_STATUS = """
query($owner: String!, $name: String!, $number: Int!, $contextsPageSize: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      title
      body
      url
      isDraft
      author { login }
      mergeable
      mergeStateStatus
      baseRefName
      headRefName
      headRefOid
      createdAt
      updatedAt
      headRepository {
        nameWithOwner
        url
      }
      baseRepository {
        nameWithOwner
        url
      }
      isCrossRepository
      maintainerCanModify
      commits(last: 1) {
        nodes {
          commit {
            oid
            statusCheckRollup {
              state
              contexts(first: $contextsPageSize) {
                nodes {
                  __typename
                  ... on CheckRun {
                    name
                    status
                    conclusion
                  }
                  ... on StatusContext {
                    context
                    state
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""
