"""initial schema

Revision ID: 0001
Revises: none
"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('articles',
    sa.Column('id', sa.String(length=16), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('source_name', sa.String(length=200), nullable=False),
    sa.Column('article_url', sa.Text(), nullable=False),
    sa.Column('image_url', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('upvotes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('downvotes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('comment_count', sa.Integer(), server_default='0', nullable=False),
    sa.CheckConstraint("category IN ('India', 'World', 'Tech', 'Sports', 'Business', 'Science')", name=op.f('ck_articles_category')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_articles'))
    )
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.create_index('ix_articles_category_published_at_id', ['category', 'published_at', 'id'], unique=False)
        batch_op.create_index('ix_articles_published_at_id', ['published_at', 'id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('display_name', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('blocks',
    sa.Column('blocker_id', sa.String(length=40), nullable=False),
    sa.Column('blocked_id', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('blocker_id <> blocked_id', name=op.f('ck_blocks_not_self')),
    sa.ForeignKeyConstraint(['blocked_id'], ['users.id'], name=op.f('fk_blocks_blocked_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['blocker_id'], ['users.id'], name=op.f('fk_blocks_blocker_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('blocker_id', 'blocked_id', name=op.f('pk_blocks'))
    )
    with op.batch_alter_table('blocks', schema=None) as batch_op:
        batch_op.create_index('ix_blocks_blocked_id', ['blocked_id'], unique=False)

    op.create_table('comments',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('article_id', sa.String(length=16), nullable=False),
    sa.Column('author_id', sa.String(length=40), nullable=False),
    sa.Column('parent_id', sa.String(length=40), nullable=True),
    sa.Column('text', sa.String(length=1000), nullable=False),
    sa.Column('upvotes', sa.Integer(), server_default='0', nullable=False),
    sa.Column('is_hidden', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], name=op.f('fk_comments_article_id_articles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_comments_author_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], name=op.f('fk_comments_parent_id_comments'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comments'))
    )
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index('ix_comments_article_id_created_at', ['article_id', 'created_at'], unique=False)
        batch_op.create_index('ix_comments_author_id_created_at', ['author_id', 'created_at'], unique=False)
        batch_op.create_index('ix_comments_parent_id', ['parent_id'], unique=False)

    op.create_table('votes',
    sa.Column('user_id', sa.String(length=40), nullable=False),
    sa.Column('article_id', sa.String(length=16), nullable=False),
    sa.Column('value', sa.String(length=4), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("value IN ('up', 'down')", name=op.f('ck_votes_value')),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], name=op.f('fk_votes_article_id_articles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_votes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'article_id', name=op.f('pk_votes'))
    )
    with op.batch_alter_table('votes', schema=None) as batch_op:
        batch_op.create_index('ix_votes_article_id', ['article_id'], unique=False)

    op.create_table('comment_reports',
    sa.Column('comment_id', sa.String(length=40), nullable=False),
    sa.Column('reporter_id', sa.String(length=40), nullable=False),
    sa.Column('reason', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("reason IN ('spam', 'abuse', 'misinformation', 'other')", name=op.f('ck_comment_reports_reason')),
    sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], name=op.f('fk_comment_reports_comment_id_comments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reporter_id'], ['users.id'], name=op.f('fk_comment_reports_reporter_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('comment_id', 'reporter_id', name=op.f('pk_comment_reports'))
    )
    with op.batch_alter_table('comment_reports', schema=None) as batch_op:
        batch_op.create_index('ix_comment_reports_reporter_id', ['reporter_id'], unique=False)

    op.create_table('comment_upvotes',
    sa.Column('user_id', sa.String(length=40), nullable=False),
    sa.Column('comment_id', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], name=op.f('fk_comment_upvotes_comment_id_comments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_comment_upvotes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'comment_id', name=op.f('pk_comment_upvotes'))
    )
    with op.batch_alter_table('comment_upvotes', schema=None) as batch_op:
        batch_op.create_index('ix_comment_upvotes_comment_id', ['comment_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('comment_upvotes', schema=None) as batch_op:
        batch_op.drop_index('ix_comment_upvotes_comment_id')

    op.drop_table('comment_upvotes')
    with op.batch_alter_table('comment_reports', schema=None) as batch_op:
        batch_op.drop_index('ix_comment_reports_reporter_id')

    op.drop_table('comment_reports')
    with op.batch_alter_table('votes', schema=None) as batch_op:
        batch_op.drop_index('ix_votes_article_id')

    op.drop_table('votes')
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_index('ix_comments_parent_id')
        batch_op.drop_index('ix_comments_author_id_created_at')
        batch_op.drop_index('ix_comments_article_id_created_at')

    op.drop_table('comments')
    with op.batch_alter_table('blocks', schema=None) as batch_op:
        batch_op.drop_index('ix_blocks_blocked_id')

    op.drop_table('blocks')
    op.drop_table('users')
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.drop_index('ix_articles_published_at_id')
        batch_op.drop_index('ix_articles_category_published_at_id')

    op.drop_table('articles')
